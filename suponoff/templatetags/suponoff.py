from django import template


def sizeof_fmt(num):
    for x in ['bytes', 'KB', 'MB', 'GB']:
        if num < 1024.0 and num > -1024.0:
            return "%3.1f%s" % (num, x)
        num /= 1024.0
    return "%3.1f%s" % (num, 'TB')

register = template.Library()


def sizeof_fmt_django(x):
	try:
		value = int(x)
	except ValueError:
		return x
	return sizeof_fmt(value)

register.filter('sizeof_fmt', sizeof_fmt_django)


@register.filter
def get_item(dictionary, key):
    return dictionary[key]
