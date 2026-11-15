from pathlib import Path
import pypdfium2 as pdfium
from pypdf import PdfReader
from PIL import Image, ImageOps, ImageDraw

here=Path(__file__).parent
pdf=pdfium.PdfDocument(here/'ResistMap_AI.pdf')
reader=PdfReader(here/'ResistMap_AI.pdf')
out=here/'rendered'
out.mkdir(exist_ok=True)
images=[]
for i in range(len(pdf)):
    im=pdf[i].render(scale=1.5).to_pil().convert('RGB')
    im.save(out/f'page-{i+1}.png')
    images.append(im)
    text=reader.pages[i].extract_text()
    assert '??' not in text, f'Unresolved reference on page {i+1}'
    print(i+1,len(text))
for start in range(0,len(images),2):
    pair=images[start:start+2]
    sheet=Image.new('RGB',(sum(x.width for x in pair),max(x.height for x in pair)+30),'#dddddd')
    offset=0
    for i,im in enumerate(pair,start+1):
        sheet.paste(im,(offset,30))
        ImageDraw.Draw(sheet).text((offset+12,8),f'Page {i}',fill='black')
        offset+=im.width
    sheet.save(out/f'review-{start+1}-{start+len(pair)}.png')
(here/'rendered_text.txt').write_text('\n\n'.join(p.extract_text() for p in reader.pages),encoding='utf-8')
print('PDF pages:',len(pdf))
