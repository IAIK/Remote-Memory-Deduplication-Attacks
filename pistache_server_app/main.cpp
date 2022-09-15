/*
   Mathieu Stefani, 07 février 2016

   Example of a REST endpoint with routing
*/

#include <algorithm>
#include <csignal>
#include <chrono>
#include <sstream>

#include <sys/mman.h>
#include <string.h>
#include <stdbool.h>

#include <pistache/http.h>
#include <pistache/router.h>
#include <pistache/endpoint.h>

using namespace std;
using namespace Pistache;

#define PAGE_SIZE (4096)
#define POSSIBLE_OFFSETS (512)
#define MAX_NUM_PAGES (6)
#define PAGES_MEM (PAGE_SIZE * POSSIBLE_OFFSETS * MAX_NUM_PAGES)

uint64_t rdtsc(){
  uint64_t a, d;
  asm volatile("lfence");
  asm volatile("rdtscp" : "=a"(a), "=d"(d) :: "rcx");
  a = (d << 32) | a;
  asm volatile("mfence");
  return a;
}

bool unhexlify(char *hex, char *bin, size_t len)
{
  size_t i;
  uint8_t c;

  for (i = 0; i < len / 2; i++) {
    c = hex[2 * i];
    if (c >= '0' && c <= '9') {
      bin[i] = (c - '0') << 4;
    } else if (c >= 'a' && c <= 'f') {
      bin[i] = (c - 'a' + 10) << 4;
    } else if (c >= 'A' && c <= 'F') {
      bin[i] = (c - 'A' + 10) << 4;
    } else {
      return false;
    }

    c = hex[2 * i + 1];
    if (c >= '0' && c <= '9') {
      bin[i] += c - '0';
    } else if (c >= 'a' && c <= 'f') {
      bin[i] += c - 'a' + 10;
    } else if (c >= 'A' && c <= 'F') {
      bin[i] += c - 'A' + 10;
    } else {
      return false;
    }
  }
  return true;
}

void printCookies(const Http::Request& req) {
  auto cookies = req.cookies();
  std::cout << "Cookies: [" << std::endl;
  const std::string indent(4, ' ');
  for (const auto& c: cookies) {
    std::cout << indent << c.name << " = " << c.value << std::endl;
  }
  std::cout << "]" << std::endl;
}

namespace Generic {

void handleReady(const Rest::Request&, Http::ResponseWriter response) {
  response.send(Http::Code::Ok, "1");
}

}

class KASLREndpoint {
public:
  explicit KASLREndpoint(Address addr)
    : httpEndpoint(std::make_shared<Http::Endpoint>(addr))
  { }

  ~KASLREndpoint() {
    if (this->pages) {
      std::cout << "Clearing pages" << std::endl;
      memset(this->pages, 0, PAGES_MEM);
      munmap(this->pages, PAGES_MEM);
    }
  }

  void init(size_t thr = 2) {
    auto opts = Http::Endpoint::options()
      .threads(static_cast<int>(thr))
      .maxRequestSize(4096*MAX_NUM_PAGES*2+4096);
    httpEndpoint->init(opts);
    setupRoutes();
    setupPages();
  }

  void start() {
    httpEndpoint->setHandler(router.handler());
    httpEndpoint->serve();
  }

  void shutdown() {
    httpEndpoint->shutdown();
  }

private:
  char* pages = nullptr;

  void setupPages() {
    this->pages = reinterpret_cast<char*>(mmap((void*) 0, PAGES_MEM, PROT_READ|PROT_WRITE, MAP_PRIVATE|MAP_ANONYMOUS|MAP_POPULATE, -1, 0));
    if (this->pages == MAP_FAILED) {
      throw "Could not mmap";
    }
  }

  void setupRoutes() {
    using namespace Rest;

    Routes::Post(router, "/set-page/:offset", Routes::bind(&KASLREndpoint::setPage, this));
    Routes::Post(router, "/set-byte/:offset", Routes::bind(&KASLREndpoint::setByte, this));
    Routes::Get(router, "/random", Routes::bind(&KASLREndpoint::random, this));
    // Routes::Get(router, "/ready", Routes::bind(&Generic::handleReady));
    // Routes::Get(router, "/auth", Routes::bind(&KASLREndpoint::doAuth, this));

  }

  void setPage(const Rest::Request& request, Http::ResponseWriter response) {
    auto offset = request.param(":offset").as<int>();

    std::cout << "[" << gettid() << "] Set page: " << offset << std::endl;

    if (offset > 511) {
      std::cout << "[" << gettid() << "] Invalid offset: " << offset << std::endl;
      response.send(Http::Code::Forbidden, std::to_string(offset));
      return;
    }

    // get data
    auto data = request.body();

    for (size_t idx = 0, i = 0; i < data.size(); idx++, i += 4096*2) {
      size_t start = offset * (MAX_NUM_PAGES * PAGE_SIZE) + (idx * PAGE_SIZE);

      char buffer[4096];
      unhexlify(&data[0] + i, buffer, 4096*2);

      memcpy(pages + start, buffer, 4096);
    }


    response.send(Http::Code::Ok, std::to_string(offset));
  }

  void setByte(const Rest::Request& request, Http::ResponseWriter response) {
    auto offset = request.param(":offset").as<int>();

    std::cout << "[" << gettid() << "] Set byte: " << offset << std::endl;

    if (offset > 511) {
      std::cout << "[" << gettid() << "] Invalid offset: " << offset << std::endl;
      response.send(Http::Code::Forbidden, std::to_string(offset));
      return;
    }

    auto start_ns = std::chrono::high_resolution_clock::now();
    uint64_t start = rdtsc();

    for (size_t idx = 0; idx < MAX_NUM_PAGES; idx++) {
      size_t start = offset * (MAX_NUM_PAGES * PAGE_SIZE) + (idx * PAGE_SIZE);
      *((volatile char*) pages+start) = *((volatile char*) pages+start);
    }

    uint64_t end = rdtsc();
    auto end_ns = std::chrono::high_resolution_clock::now();

    uint64_t diff = end - start;
    auto diff_ns = end_ns - start_ns;

    std::ostringstream r;
    r << diff << "," << diff_ns.count();

    response.send(Http::Code::Ok, r.str());
  }

  void random(const Rest::Request& request, Http::ResponseWriter response) {
    response.send(Http::Code::Ok, "OK");
  }

  std::shared_ptr<Http::Endpoint> httpEndpoint;
  Rest::Router router;
};

static KASLREndpoint* server = nullptr;

void signalHandler(int signum)
{
  server->shutdown();
  delete server;

  exit(0);
}

int main(int argc, char *argv[]) {
  Port port(6666);

  int thr = 2;

  if (argc >= 2) {
    port = static_cast<uint16_t>(std::stol(argv[1]));

    if (argc == 3)
      thr = std::stoi(argv[2]);
  }

  Address addr(Ipv4::any(), port);

  cout << "Cores = " << hardware_concurrency() << endl;
  cout << "Using " << thr << " threads" << endl;

  signal(SIGINT, signalHandler);

  server = new KASLREndpoint(addr);

  server->init(thr);
  server->start();
}

