import csv, random, re
from pathlib import Path

HERE=Path(__file__).parent
ROOT=HERE.parents[1]
with open(ROOT/'results/ceftazidime_v2_20261001T202849_616568Z/development_oof_probabilities.csv', newline='') as f:
    data=[r for r in csv.DictReader(f) if r['candidate']=='RF_leaf_4']
rng=random.Random(42)
coords={0:[],1:[]}
for row in data:
    x=int(row['fold'])+rng.uniform(-.19,.19)
    coords[int(row['actual'])].append(f"({x:.5f},{float(row['probability_R']):.7f})")
fig=r'''\begin{figure}[t]
\centering
\begin{tikzpicture}
\begin{axis}[width=\columnwidth,height=5.5cm,xmin=0.5,xmax=3.5,ymin=-0.02,ymax=1.02,xtick={1,2,3},xlabel={Development fold (horizontal jitter)},ylabel={Predicted resistance probability},tick label style={font=\scriptsize},label style={font=\small},legend style={font=\scriptsize,at={(0.5,1.02)},anchor=south,legend columns=2},ymajorgrids,grid style={gray!20}]
'''
for label,color,marker in [(0,'resblue','o'),(1,'resorange','+')]:
    fig+=r'\addplot[only marks,mark='+marker+',mark size=1.4pt,color='+color+'] coordinates {'+' '.join(coords[label])+'};\n'
fig+=r'''\addplot[black,dashed,thick,forget plot] coordinates {(0.5,0.4)(3.5,0.4)};
\legend{Actual susceptible,Actual resistant}
\end{axis}
\end{tikzpicture}
\caption{Out-of-fold predictions for all 445 development isolates. The dashed line is the selected threshold of 0.40. Horizontal jitter is for visibility only.}
\label{fig:scatter}
\end{figure}'''
p=HERE/'ResistMap_AI.tex'
tex=p.read_text(encoding='utf-8').replace('% SCATTER_FIGURE',fig)
tex=tex.replace('evaluates 52 configurations','evaluates 28 configurations').replace('and 24 configurations for each','and 12 configurations for each')
p.write_text(tex,encoding='utf-8')
abstract=re.search(r'\\begin\{abstract\}(.*?)\\end\{abstract\}',tex,re.S).group(1)
refs=re.findall(r'\\bibitem\{([^}]+)\}',tex)
cites=[c for group in re.findall(r'\\cite\{([^}]+)\}',tex) for c in group.split(',')]
assert 150<=len(abstract.split())<=200
assert len(refs)==18 and set(refs)==set(cites)
assert len(re.findall(r'\\section\{',tex))==6
assert len(re.findall(r'\\begin\{figure\}',tex))==3
assert len(re.findall(r'\\begin\{table\}',tex))==2
print({'abstract_words':len(abstract.split()),'references':len(refs),'sections':6,'figures':3,'tables':2,'scatter_points':len(data),'source_characters':len(tex)})
