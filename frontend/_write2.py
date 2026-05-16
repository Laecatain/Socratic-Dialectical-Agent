import codecs
lines = [
    '<!doctype html>',
    '<html lang="zh-CN">',
    '  <head>',
    '    <meta charset="UTF-8" />',
    '    <meta name="viewport" content="width=device-width, initial-scale=1.0" />',
    '    <title>\u82cf\u683c\u62c9\u5e95\u8fa9\u8bc1\u5bf9\u8bdd</title>',
    '  </head>',
    '  <body>',
    '    <div id="root"></div>',
    '    <script type="module" src="/src/main.tsx"></script>',
    '  </body>',
    '</html>',
    '',
]
path = r'E:\app\Socratic Dialectical Agent\frontend\index.html'
with codecs.open(path, 'w', 'utf-8') as f:
    f.write('\n'.join(lines))
print('OK')
