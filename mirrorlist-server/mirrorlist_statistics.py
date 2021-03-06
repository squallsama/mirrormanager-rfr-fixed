#!/usr/bin/env python
#
# Copyright (C) 2008 by Alexander Koenig
# Copyright (C) 2008, 2009 by Adrian Reber
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

import sys, pylab, time, getopt

start = time.clock()

logfile = None
dest = None
offset = 0

def usage():
	print "mirrorlist_statistics.py analyzes mirrorlist_server.py logfiles"
	print "and draws piecharts"
	print
	print "Usage:"
	print "  mirrorlist_statistics.py [OPTION]..."
	print
	print "Options:"
	print "  -l, --log=LOGFILE     logfile which should be used as input"
	print "  -d, --dest=DIRECTORY  output directory"
	print "  -o, --offset=DAYS     number of days which should be subtracted"
	print "                        from today's date and be used as basis for log analysis"
	print "  -h, --help            show this help; then exit"
	print

def parse_args():
	global logfile
	global dest
	global offset
	opts, args = getopt.getopt(sys.argv[1:], "l:d:ho:",
				["log=", "dest=", "help", "offset"])
	for option, argument in opts:
		if option in ("-l", "--log"):
			logfile = argument
		if option in ("-d", "--dest"):
			dest = argument
		if option in ("-o", "--offset"):
			offset = int(argument)
		if option in ("-h", "--help"):
			usage()
			sys.exit(0)

parse_args()

if logfile is None or dest is None:
	usage()
	sys.exit(-1)
	
def sort_dict(dict):
    """ Sort dictionary by values and reverse. """
    items=dict.items()
    sorteditems=[[v[1],v[0]] for v in items ]
    sorteditems.sort()
    sorteditems.reverse()
    return sorteditems


y1, m1, d1, x1, x2, x3, x4, x5, x6 = time.localtime()

# this works only if offset < d1
if d1 > offset:
	d1 = d1 - offset

countries = {}
accesses = 0
repositories = {}
archs = {}
i = 0

for line in open(logfile):
	arguments = line.split()
	try:
		y, m, d = arguments[3][:10].split('-')
	except:
		continue
        if not ((int(y) == y1) and (int(m) == m1) and (int(d) == d1)):
		continue
	try:
		countries[arguments[5][:2]] += 1
	except:
		countries[arguments[5][:2]] = 1
	try:
		archs[arguments[9]] += 1
	except:
		archs[arguments[9]] = 1
	try:
		repositories[arguments[7][:len(arguments[7])-1]] += 1
	except:
		repositories[arguments[7][:len(arguments[7])-1]] = 1
	accesses += 1
	continue

def do_pie(prefix, dict, accesses):
	pylab.figure(1, figsize=(8,8))
	ax =  pylab.axes([0.1, 0.1, 0.8, 0.8])

	labels = []
	fracs = []
	rest = 0

	for item in dict.keys():
		frac = dict[item]

		if (float(frac)/float(accesses) > 0.01):
			labels.append(item)
			fracs.append(frac)
		else:
			rest += frac

	i = 0
	changed = False
	for x in labels:
		if x == 'undef':
			fracs[i] += rest
			labels[i] = 'other'
			changed = True
		i += 1

	if changed == False:
		labels.append('other')
		fracs.append(rest)

	pylab.pie(fracs, labels=labels, autopct='%1.1f%%', pctdistance=0.75, shadow=True)
	pylab.savefig('%s%s-%d-%02d-%02d.png' % (dest, prefix, y1, m1, d1))
	pylab.close(1)


def write_size(html, size):
	if size/1024 <= 0:
		html.write('%.2f Bytes'  % (size))
	elif size/1024/1024 <= 0:
		html.write('%.2f KB'  % (size/1024.00))
	elif size/1024/1024/1024 <= 0:
		html.write('%.2f MB'  % (size/1024.00/1024.00))
	elif size/1024/1024/1024/1024 <= 0:
		html.write('%.2f GB'  % (size/1024.00/1024.00/1024.00))
	else:
		html.write('%.2f TB'  % (size/1024.00/1024.00/1024.00/1024.00))

def background(html, css_class, toggle):
	html.write('\t<tr')
	if toggle:
		html.write(' class="%s"' % css_class)
		toggle = False
	else:
		toggle = True
	html.write('>\n\t')
	return toggle

def do_html(prefix, dict, accesses):
	html = open('%s%s-%d-%02d-%02d.txt' % (dest, prefix, y1, m1, d1), 'w')
	html.write('<img src="data/%s-%d-%02d-%02d.png" border="0" alt="alt"/>\n' % (prefix, y1, m1, d1))
	html.write('<h2>Details</h2>\n')
	html.write('<table class="altrows" align="center">\n')
	html.write('<tr><th class="statusth">Mirror Name</th><th class="statusth">%</th>')
	html.write('<th class="statusth">#Requests</th></tr>\n')

	toggle = False

	for item in sort_dict(dict):
		size = item[0]
		toggle = background(html, 'odd', toggle)
		html.write('<td>%s</td>\n' % (item[1]))
		html.write('\t<td align="right">%05.4lf %%</td>\n' % ((float(size)/float(accesses))*100))
		html.write('<td align="right">')
		html.write('%d' % (size))
		html.write('</td></tr>\n')

	# print the overall information
	background(html, 'total', True)
	html.write('<th>Total</th><th>\n');
	html.write('</th><th align="right">%d' % (accesses))
	html.write('</th></tr>\n');

	html.write('</table>\n')
	end = time.clock()
	html.write('<p>Last updated: %s GMT' % time.strftime("%a, %d %b %Y %H:%M:%S",time.gmtime()))
	html.write(' (runtime %ss)</p>\n' % (end-start))

do_pie('countries', countries, accesses)
do_pie('archs', archs, accesses)
do_pie('repositories', repositories, accesses)

do_html('countries', countries, accesses)
do_html('archs', archs, accesses)
do_html('repositories', repositories, accesses)
