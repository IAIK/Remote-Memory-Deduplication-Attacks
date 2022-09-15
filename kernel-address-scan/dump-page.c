/* See LICENSE file for license and copyright information */

#define _GNU_SOURCE

#include <stdio.h>
#include <stdlib.h>
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

#define LENGTH(x) (sizeof(x)/sizeof((x)[0]))

static void
print_help(char* argv[]) {
  fprintf(stdout, "Usage: %s [OPTIONS]\n", argv[0]);
  fprintf(stdout, "\t-o, -output-file\t\t Output file\n");
  fprintf(stdout, "\t-h, -help\t\t Help page\n");
}

int main(int argc, char* argv[])
{
  /* Define parameters */
  FILE* output_file = NULL;

  /* Parse arguments */
  static const char* short_options = "h:o:";
  static struct option long_options[] = {
    {"help",        no_argument,       NULL, 'h'},
    {"output-file", required_argument, NULL, 'o'},
    { NULL,         0, NULL,  0}
  };

  int c;
  while ((c = getopt_long(argc, argv, short_options, long_options, NULL)) != -1) {
    switch (c) {
      case 'h':
        print_help(argv);
        return 0;
      case ':':
        fprintf(stderr, "Error: option `-%c' requires an argument\n", optopt);
        break;
      case 'o':
        {
          output_file = fopen(optarg, "w");
	  if (output_file == NULL) {
            fprintf(stderr, "Error: Could not open output file\n");
	    return -1;
	  }
	}
        break;
      case '?':
      default:
        fprintf(stderr, "Error: Invalid option '-%c'\n", optopt);
        return -1;
    }
  }

  if (argv[optind] == NULL) {
    fprintf(stderr, "Error: PFN argument required.\n");
    return -1;
  }

  size_t pfn = strtoull(argv[optind], NULL, 0);
  fprintf(stderr, "%zu\n", pfn);

  /* Setup */
  if (ptedit_init()) {
    printf("Error: Could not initalize PTEditor, did you load the kernel module?\n");
    return 1;
  }

  char content[4096];
  ptedit_read_physical_page(pfn, (char*) content);

  for (size_t i = 0; i < 4096; i++) {
    if (i % 16 == 0) {
      fprintf(stdout, "%3x: ", (int) i);
    }

    /* check if address */
    bool is_address = false;
    if (i > 7 && i < 4088) {
      for (int shift = -7; shift <= 0; shift++) {
        size_t address;
        memcpy(&address, (char*) content + i + shift, sizeof(size_t));

        if (address > 0xffffffff80000000ull && address < 0xfffffffffeffffffull) {
          is_address = true;
        }
      }
    }

    if (is_address == true) {
      fprintf(stdout, COLOR_GREEN);
    } else {
      if (content[i] != 0) {
        fprintf(stdout, COLOR_YELLOW);
      }
    }

    fprintf(stdout, "%02x ", content[i] & 0xFF);

    fprintf(stdout, COLOR_RESET);

    if (i % 16 == 15) {
      fprintf(stdout, "\n");
    }
  }

  if (output_file != NULL) {
    fwrite(content, 4096, 1, output_file);
    fclose(output_file);
  }

  /* Clean-up */
  ptedit_cleanup();

  return 0;
}

