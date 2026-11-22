import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import agent_bridge


class P4RetrievalSelectionTests(unittest.TestCase):
    def test_default_is_p4_bundled_retrieval(self):
        with patch.dict(os.environ,{'P3_RAG_PATH':''}):
            self.assertEqual(agent_bridge.rag_path(),(agent_bridge.P4_ROOT/'p3_retrieval').resolve())
        requirements=(Path(__file__).resolve().parents[1]/'requirements.txt').read_text()
        self.assertIn('../p4-agent/p3_retrieval/requirements.txt',requirements)
        self.assertNotIn('../p3-retrieval/',requirements)

    def test_explicit_external_layout_is_checked_relative_to_its_own_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for relative in ('retrieve.py','index/bm25.pkl','index/faiss.index','index/chunk_ids.json'):
                file=root/relative
                file.parent.mkdir(exist_ok=True)
                file.touch()
            with patch.dict(os.environ,{'P3_RAG_PATH':directory,'LLM_TARGET':'local','LLM_BASE_URL':''}):
                self.assertEqual(agent_bridge.rag_path(),root.resolve())
                self.assertIn('parsed/all_chunks.jsonl',agent_bridge.missing_setup())
                (root/'parsed').mkdir()
                (root/'parsed/all_chunks.jsonl').touch()
                self.assertNotIn('parsed/all_chunks.jsonl',agent_bridge.missing_setup())


if __name__=='__main__': unittest.main()
