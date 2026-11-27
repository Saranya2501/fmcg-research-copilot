from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'integration'))
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'integration'/'p2_agents'))
from runtime import normalize_chunks
from schemas import Chunk

def test_normalize_p3_chunk_contract():
    source=[{"chunk_id":"x1","doc_id":"doc1","company":"HUL","fiscal_year":"FY24","page":9,"text":"Revenue 10","score":.9}]
    out=normalize_chunks(source,Chunk)
    assert len(out)==1
    assert out[0].chunk_id=="x1"
    assert out[0].doc=="doc1"
    assert out[0].page==9

def test_normalize_alternate_fields():
    out=normalize_chunks([{"id":"x2","document":"report.pdf","company":"ITC","content":"Text"}],Chunk)
    assert out[0].chunk_id=="x2" and out[0].doc=="report.pdf" and out[0].text=="Text"
