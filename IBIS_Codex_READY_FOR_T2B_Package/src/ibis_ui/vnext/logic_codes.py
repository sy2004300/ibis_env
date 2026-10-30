"""Signal code presentation and conversion; existing canonical logic rules remain shared."""
from __future__ import annotations
import copy
import re
from ibis_auto.values import parse_logic, normalize_logic_text
from .model import CORNERS

BASES = {'二进制': ('b', 2), '十进制': ('d', 10), '十六进制': ('h', 16)}


def number(raw, radix=None, width=None):
    value = normalize_logic_text(str(raw))
    if radix is not None and radix not in BASES:
        raise ValueError('进制必须选择二进制、十进制或十六进制')
    declared = None
    match = re.fullmatch(r"(\d+)'([bBhHdD])([0-9a-fA-F_]+)", value)
    if match:
        declared = int(match.group(1))
        base = {'b':2, 'd':10, 'h':16}[match.group(2).lower()]
        digits = match.group(3)
    elif value.lower().startswith(('0b', '0x')):
        base = 2 if value[1].lower() == 'b' else 16
        digits = value[2:]
    else:
        if any(mark in value for mark in ("'", '"', '`', '“', '”')):
            raise ValueError('代码值含无法识别的引号；请填写纯数值，或使用标准 4\'b1111 格式')
        if radix is not None and radix not in BASES:
            raise ValueError('进制必须选择二进制、十进制或十六进制')
        base = BASES[radix][1] if radix else 10  # Legacy bare digits are decimal.
        digits = value
    pattern = {2:r'[01]+', 10:r'[0-9]+', 16:r'[0-9a-fA-F]+'}[base]
    digits = digits.replace('_', '')
    if not re.fullmatch(pattern, digits):
        raise ValueError('%s代码值格式非法：%s' % ({2:'二进制',10:'十进制',16:'十六进制'}[base], raw))
    result = int(digits, base)
    if declared is not None and (declared <= 0 or result.bit_length() > declared):
        raise ValueError('代码值超出声明的 %s-bit 位宽' % declared)
    if width is not None and (result.bit_length() > width or (declared is not None and declared > width)):
        raise ValueError('代码值 %s 超出 MSI %s-bit 位宽（最大值 %s）' % (raw, width, 2 ** width - 1))
    return result


def radix_for(row):
    if row.get('radix'):
        return str(row['radix']).strip()
    if row.get('encoding')=='code':
        return '二进制'
    for corner in CORNERS:
        value = normalize_logic_text(str(row.get(corner, '')))
        if not value:
            continue
        if re.match(r"^\d+'[hH]", value) or value.lower().startswith('0x'):
            return '十六进制'
        if re.match(r"^\d+'[bB]", value) or value.lower().startswith('0b'):
            return '二进制'
        return '十进制'
    return '二进制'


def widths_for(row, resolved, global_signal=False):
    target = str(row.get('signal', '')).casefold()
    return sorted({int(s['width']) for module, signals in resolved.get('msi', {}).items()
                   if global_signal or module == row.get('module')
                   for s in signals if s['name'].casefold() == target})


def format_number(value, radix, width=None):
    if radix not in BASES:
        raise ValueError('进制必须选择二进制、十进制或十六进制')
    if radix == '二进制':
        return format(value, 'b').zfill(width or 1)
    if radix == '十六进制':
        return format(value, 'X')
    return str(value)


def display_row(row, resolved, global_signal=False):
    shown = copy.deepcopy(row)
    widths = widths_for(row, resolved, global_signal)
    width = min(widths) if widths else None
    radix = radix_for(row)
    shown.update(width=' / '.join(str(w) for w in widths), radix=radix)
    for corner in CORNERS:
        raw = str(row.get(corner, '')).strip()
        if not raw:
            shown[corner] = ''
            continue
        try:
            value = number(raw, radix if row.get('encoding')=='code' else None, width)
            shown[corner] = format_number(value, radix, width)
        except ValueError:
            shown[corner] = raw  # Incomplete/invalid data must remain editable/exportable.
    return shown


def change_radix(row, radix, resolved, global_signal=False):
    """Atomic value-preserving conversion. Never reinterpret the old digit string."""
    widths = widths_for(row, resolved, global_signal)
    width = min(widths) if widths else None
    converted = {}
    for corner in CORNERS:
        raw = str(row.get(corner, '')).strip()
        converted[corner] = format_number(number(raw, radix_for(row) if row.get('encoding')=='code' else None, width), radix, width) if raw else ''
    row.update(converted)
    row.update(radix=radix, encoding='code')


def edit_code(row, corner, text, resolved, global_signal=False):
    if row.get('encoding') != 'code':
        shown = display_row(row, resolved, global_signal)
        row.update({c:shown[c] for c in CORNERS})
        row.update(radix=shown['radix'], encoding='code')
    row[corner] = str(text).strip()
    widths = widths_for(row, resolved, global_signal)
    value = number(row[corner], row['radix'], min(widths) if widths else None) if row[corner] else None
    if value is not None:
        row[corner] = format_number(value, row['radix'], min(widths) if widths else None)


def canonical_value(row, corner, width):
    raw = str(row.get(corner, '')).strip()
    if not raw:
        return ''
    if row.get('encoding') == 'code':
        radix = radix_for(row)
        value = number(raw, radix, width)
        text = "%s'%s%s" % (width, BASES[radix][0], format_number(value, radix, width))
    else:
        # Preserve valid legacy literal spelling (and therefore all old Core rules).
        text = normalize_logic_text(raw)
    parse_logic(text, str(row.get('module', '全局')), str(row.get('signal', '')), width)
    return text
