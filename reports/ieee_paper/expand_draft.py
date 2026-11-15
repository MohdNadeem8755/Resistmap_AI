from pathlib import Path
import difflib

here=Path(__file__).parent
p=here/'ResistMap_AI.tex'
old=p.read_text(encoding='utf-8')
(here/'ResistMap_AI_before_expansion.tex').write_text(old,encoding='utf-8')
new=old
for marker,filename in [(r'\section{Experimental Setup}','add_methods.tex'),(r'\section{Results and Discussion}','add_setup.tex'),(r'\section{Conclusion}','add_results.tex')]:
    assert new.count(marker)==1
    new=new.replace(marker,(here/filename).read_text(encoding='utf-8')+'\n'+marker)
diff=list(difflib.unified_diff(old.splitlines(),new.splitlines(),fromfile='before',tofile='expanded',lineterm=''))
assert not any(line.startswith('-') and not line.startswith('---') for line in diff)
p.write_text(new,encoding='utf-8')
(here/'expansion.diff').write_text('\n'.join(diff),encoding='utf-8')
print('Verified additive-only edit: no original lines removed or rewritten.')
print('Added characters:',len(new)-len(old))
