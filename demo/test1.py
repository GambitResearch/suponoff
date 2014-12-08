import gc
import time

while 1:
	l = []
	for i in xrange(10000000):
		l.append("foo")
	time.sleep(1)
