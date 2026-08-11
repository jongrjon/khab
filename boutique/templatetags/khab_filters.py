from django import template

register = template.Library()

@register.filter
def isk(value):
    """Format a number with Icelandic thousand separator (dot)."""
    try:
        num = int(value)
        negative = num < 0
        num = abs(num)
        formatted = '{:,}'.format(num).replace(',', '.')
        if negative:
            return '-' + formatted
        return formatted
    except (ValueError, TypeError):
        return value
