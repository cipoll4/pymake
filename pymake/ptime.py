#!/usr/bin/env python

if __name__ == "__main__":
	import sys
	import pstats

	stats = pstats.Stats(sys.argv[1])
	stats.strip_dirs()
	stats.sort_stats('cumulative')
	stats.print_stats()

