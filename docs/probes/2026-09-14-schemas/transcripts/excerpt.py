#!/usr/bin/env python3
# Prints raw line N (0-based) of a capture file, byte-for-byte except that JSON string literals longer than
# MAX chars are cut and marked with "...". Usage: excerpt.py FILE N [MAX]
import re, sys
f, n = sys.argv[1], int(sys.argv[2]); mx = int(sys.argv[3]) if len(sys.argv) > 3 else 80
line = open(f, encoding='utf-8').read().split('\n')[n]
print(re.sub(r'"((?:[^"\\]|\\.)*)"', lambda m: '"' + m.group(1)[:mx] + '..."' if len(m.group(1)) > mx else m.group(0), line))
