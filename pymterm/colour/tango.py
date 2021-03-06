TANGO_PALLETE = [
    '2e2e34343636',
    'cccc00000000',
    '4e4e9a9a0606',
    'c4c4a0a00000',
    '34346565a4a4',
    '757550507b7b',
    '060698989a9a',
    'd3d3d7d7cfcf',
    '555557575353',
    'efef29292929',
    '8a8ae2e23434',
    'fcfce9e94f4f',
    '72729f9fcfcf',
    'adad7f7fa8a8',
    '3434e2e2e2e2',
    'eeeeeeeeecec',
]

def parse_tango_color(c):
    r = int(c[:4][:2], 16)
    g = int(c[4:8][:2], 16)
    b = int(c[8:][:2], 16)

    return [r, g, b, 0xFF]

def apply_color(cfg, color_table):
    cfg.default_foreground_color = parse_tango_color('eeeeeeeeecec')
    cfg.default_background_color = parse_tango_color('323232323232')
    cfg.default_cursor_color = cfg.default_foreground_color

    for i in range(len(TANGO_PALLETE)):
        if i < len(color_table):
            color_table[i] = parse_tango_color(TANGO_PALLETE[i])

