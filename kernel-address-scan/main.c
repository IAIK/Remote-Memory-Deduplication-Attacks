/* See LICENSE file for license and copyright information */

#define _GNU_SOURCE

#include <stdio.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <sched.h>
#include <sys/types.h>
#include <signal.h>
#include <unistd.h>
#include <pthread.h>
#include <getopt.h>

#include "ptedit_header.h"

#define COLOR_RED     "\x1b[31m"
#define COLOR_GREEN   "\x1b[32m"
#define COLOR_YELLOW  "\x1b[33m"
#define COLOR_BLUE    "\x1b[34m"
#define COLOR_MAGENTA "\x1b[35m"
#define COLOR_CYAN    "\x1b[36m"
#define COLOR_RESET   "\x1b[0m"
#define COLOR_WHITE   "\x1b[0m"

#define MIN(a, b) ((a) > (b)) ? (b) : (a)
#define _STR(x) #x
#define STR(x) _STR(x)

typedef struct filter_s {
  const char* name;
  ptedit_pte_t set;
  ptedit_pte_t unset;
  size_t memory_type;
} filter_t;

#define LENGTH(x) (sizeof(x)/sizeof((x)[0]))
#define KERNEL_TEXT_MAPPING 0xffffffff80000000ull
#define STEP_1G (0x40000000ull)
#define STEP_512M (0x20000000ull)
#define OUTPUT_FILE "log.csv"

static size_t extend(size_t val) {
    if (val & (1ull << 47)) {
      val |= 0xffff000000000000ull;
    }

    return val;
}

typedef size_t table_t[512];

#define IS_PRESENT(entry) !!(entry & (1 << PTEDIT_PAGE_BIT_PRESENT))
#define IS_PAGE(entry) !!(entry & (1 << PTEDIT_PAGE_BIT_PSE))

typedef enum {
  PT_TYPE_PGD = 0,
  PT_TYPE_PUD,
  PT_TYPE_PMD,
  PT_TYPE_PT,
} pt_type;

typedef enum address_type_e {
  ADDRESS_KERNEL,
  ADDRESS_MODULE,
  ADDRESS_DIRECT
} address_type_t;

typedef struct symbol_cache_s {
  char name[KALLSYMS_MAX_SYMBOL_LENGTH];
  size_t address;
} symbol_cache_t;

#define SYMBOL_CACHE_SIZE (32)
symbol_cache_t symbol_cache[SYMBOL_CACHE_SIZE] = {0};
static size_t n_symbol_cache_entries = 0;
static size_t tmp_n = 0;
static size_t page_counter = 0;
static bool nokaslr = false;

symbol_cache_t symbol_cache_lookup(size_t address) {
  /* Lookup */
  for (int i = n_symbol_cache_entries - 1; i >= 0; i--) {
    if (symbol_cache[i].address == address) {
      return symbol_cache[i];
    }
  }

  int use_index = 0;
  if (n_symbol_cache_entries < SYMBOL_CACHE_SIZE - 1) {
    use_index = ++n_symbol_cache_entries;
  } else {
    use_index = (tmp_n++) % SYMBOL_CACHE_SIZE;
  }

  if (ptedit_kallsyms_lookup_address(address, symbol_cache[use_index].name) == 0) {
    symbol_cache[use_index].address = address;
  } else {
    symbol_cache[use_index].name[0] = '\0';
  };

  return symbol_cache[0];
}

static bool match_filter(FILE* log, pt_type type, size_t entry) {
  if (type != PT_TYPE_PT) {
    // skip non 4k for now
    return false;
  }
  size_t pfn = ptedit_get_pfn(entry);

  char content[4096] = {0};
  ptedit_read_physical_page(pfn, (char*) &content);

  bool print_page = false;
  for (size_t offset = 0; offset < 4095 - sizeof(size_t); offset++) {
    /* extract address */
    size_t address;
    memcpy(&address, content + offset, sizeof(size_t));

    address_type_t address_type;

    /* check if address is in bounds */
    if (nokaslr == false) {
      if (address >= 0xffff888000000000ull && address <= 0xffffc87fffffffffull) {
        // direct mapping of all physical memory (page_offset_base)
        address_type = ADDRESS_DIRECT;
        continue; // skip for now
      } else if (address >= KERNEL_TEXT_MAPPING && address <= (KERNEL_TEXT_MAPPING + STEP_1G)) {
        // kernel text mapping, mapped to physical address 0
        address_type = ADDRESS_KERNEL;
      } else if (address >= (KERNEL_TEXT_MAPPING + STEP_1G) && address <= (KERNEL_TEXT_MAPPING + 2 * STEP_1G)) {
        // module mapping space
        address_type = ADDRESS_MODULE;
      } else {
        continue;
      }
    } else {
      if (address >= 0xffff888000000000ull && address <= 0xffffc87fffffffffull) {
        // direct mapping of all physical memory (page_offset_base)
        address_type = ADDRESS_DIRECT;
        continue; // skip for now
      } else if (address >= 0xffffffff80000000ull && address <= (0xffffffff9fffffffull)) {
        // kernel text mapping, mapped to physical address 0
        address_type = ADDRESS_KERNEL;
      /* } else if (address >= (KERNEL_TEXT_MAPPING + STEP_512M) && address <= (KERNEL_TEXT_MAPPING + 3 * STEP_512M)) { */
      } else if (address >= (0xffffffffa0000000ull) && address <= (0xfffffffffeffffffull)) {
        // module mapping space
        address_type = ADDRESS_MODULE;
      } else {
        continue;
      }
    }

    if (print_page == false) {
      fprintf(stdout, "PFN: %p\n", (void*) pfn);
      print_page = true;
    }

    symbol_cache_t symbol = symbol_cache_lookup(address);
    fprintf(log, "%p,%zu,%p,%d,%s\n", (void*) pfn, offset, (void*) address, address_type, symbol.name);
  }

  return false;
}

static void print_entry(pt_type type, size_t addr, size_t entry) {
  /* Print address */
  switch (type) {
    case PT_TYPE_PT:
      fprintf(stderr, "PTE");
      break;
    case PT_TYPE_PMD:
      fprintf(stderr, "PMD");
      break;
    case PT_TYPE_PUD:
      fprintf(stderr, "PUD");
      break;
    case PT_TYPE_PGD:
      fprintf(stderr, "PGD");
      break;
  }

  fprintf(stderr, ": %p\n", (void*) addr);
}

static void
print_help(char* argv[]) {
  fprintf(stdout, "Usage: %s [OPTIONS]\n", argv[0]);
  fprintf(stdout, "\t-t, -kernel-text-mapping\t\t Kernel Text Mapping (default: " STR(KERNEL_TEXT_MAPPING) ")\n");
  fprintf(stdout, "\t-o, -output\t\t Output file (default: " STR(OUTPUT_FILE) "\n");
  fprintf(stdout, "\t-h, -help\t\t Help page\n");
}

int main(int argc, char* argv[])
{
  /* Default arguments */
  size_t kernel_text_mapping = KERNEL_TEXT_MAPPING;
  char* logfile = OUTPUT_FILE;

  /* Parse arguments */
  static const char* short_options = "t:o:kh";
  static struct option long_options[] = {
    {"kernel-text-mapping", required_argument, NULL, 't'},
    {"nokaslr",             no_argument,       NULL, 'k'},
    {"logfile",             required_argument, NULL, 'o'},
    {"help",                no_argument,       NULL, 'h'},
    { NULL,                 0,                 NULL, 0}
  };

  int c;
  while ((c = getopt_long(argc, argv, short_options, long_options, NULL)) != -1) {
    switch (c) {
      case 't':
        kernel_text_mapping = strtoull(optarg, NULL, 0);
        break;
      case 'o':
        logfile = optarg;
        break;
      case 'k':
        nokaslr = true;
        break;
      case 'h':
        print_help(argv);
        return 0;
      case ':':
        fprintf(stderr, "Error: option `-%c' requires an argument\n", optopt);
        break;
      case '?':
      default:
        fprintf(stderr, "Error: Invalid option '-%c'\n", optopt);
        return -1;
    }
  }

  /* Setup */
  if (ptedit_init()) {
    printf("Error: Could not initalize PTEditor, did you load the kernel module?\n");
    return 1;
  }

  FILE* f = fopen(logfile, "w");
  fprintf(f, "PFN,Offset,Address,Type,Symbol\n");

  size_t root = ptedit_get_paging_root(0);
  ptedit_entry_t text_mapping = ptedit_resolve((void*) kernel_text_mapping, 0);

  table_t pgd;
  ptedit_read_physical_page(root / 4096, (char*) &pgd);

  for(size_t pgd_index = 0; pgd_index < 512; pgd_index++) {
    size_t pgd_entry = pgd[pgd_index];

    if (IS_PRESENT(pgd_entry) == 0) {
      continue;
    }

    if (pgd_entry != text_mapping.pgd) {
      continue;
    }

    table_t pud;
    ptedit_read_physical_page(ptedit_get_pfn(pgd_entry), (char*) &pud);

    for(size_t pud_index = 0; pud_index < 512; pud_index++) {
      size_t pud_entry = pud[pud_index];

      if (IS_PRESENT(pud_entry) == 0) {
        continue;
      }

      if (IS_PAGE(pud_entry) == 1) { // 1 GB page
        if (match_filter(f, PT_TYPE_PUD, pud_entry) == true) {
          print_entry(PT_TYPE_PUD,
              extend((pud_index << 30) | (pgd_index << 39)),
              pud_entry
              );
        }
      } else {
        table_t pmd;
        ptedit_read_physical_page(ptedit_get_pfn(pud_entry), (char*) &pmd);

        for(size_t pmd_index = 0; pmd_index < 512; pmd_index++) {
          size_t pmd_entry = pmd[pmd_index];

          if (IS_PRESENT(pmd_entry) == 0) {
            continue;
          }

          if (IS_PAGE(pmd_entry) == 1) { // 2M page
            if (match_filter(f, PT_TYPE_PMD, pmd_entry) == true) {
              print_entry(PT_TYPE_PMD,
                  extend((pmd_index << 21) | (pud_index << 30) | (pgd_index << 39)),
                  pmd_entry
                  );
            }
          } else {
            table_t pt;
            ptedit_read_physical_page(ptedit_get_pfn(pmd_entry), (char*) &pt);

            for(size_t pt_index = 0; pt_index < 512; pt_index++) {
              size_t pt_entry = pt[pt_index];

              if (IS_PRESENT(pt_entry) == 0) {
                continue;
              }

              page_counter++;

              if (match_filter(f, PT_TYPE_PT, pt_entry) == true) {
                print_entry(PT_TYPE_PT,
                    extend((pt_index << 12) | (pmd_index << 21) | (pud_index << 30) | (pgd_index << 39)),
                    pt_entry
                    );
              }
            }
          }
        }
      }
    }
  }

  fprintf(stderr, "%zu\n", page_counter);

  /* Clean-up */
  ptedit_cleanup();

  return 0;
}

