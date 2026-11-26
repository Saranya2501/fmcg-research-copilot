import builtins
import os
import runpy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from integrations import agent_bridge


class P4RetrievalSelectionTests(unittest.TestCase):
    def test_company_aliases_match_corpus_labels_and_preserve_year_filter(self):
        retrieval = agent_bridge.load_retrieval(agent_bridge.P4_ROOT / 'p3_retrieval')
        chunks = {
            'hul24': {'company': 'HUL', 'fiscal_year': 'FY24'},
            'hul23': {'company': 'HUL', 'fiscal_year': 'FY23'},
            'dabur24': {'company': 'Dabur', 'fiscal_year': 'FY24'},
        }
        with patch.object(retrieval, '_chunk_map', chunks):
            for company in ('HUL', 'Hindustan Unilever', 'Hindustan Unilever Limited'):
                with self.subTest(company=company):
                    self.assertEqual(
                        retrieval._apply_filters(list(chunks), {'company': company, 'fiscal_year': 'FY24'}),
                        ['hul24'],
                    )

    def test_default_is_p4_bundled_retrieval(self):
        with patch.dict(os.environ,{'P3_RAG_PATH':''}):
            self.assertEqual(agent_bridge.rag_path(),(agent_bridge.P4_ROOT/'p3_retrieval').resolve())
        requirements=(Path(__file__).resolve().parents[1]/'requirements.txt').read_text()
        self.assertIn('faiss-cpu',requirements)
        self.assertIn('rank-bm25',requirements)
        self.assertNotIn('-r ',requirements)
        for excluded in ('sentence-transformers', 'torch', 'pytest', 'pymupdf', 'pdfplumber', 'langgraph', 'python-docx'):
            self.assertNotIn(excluded,requirements.lower())
        self.assertNotIn('../p3-retrieval/',requirements)

    def test_api_retrieval_does_not_import_local_models(self):
        original_import = builtins.__import__

        def import_without_local_models(name, *args, **kwargs):
            if name == 'sentence_transformers' or name.startswith('sentence_transformers.'):
                raise ImportError('Local models intentionally absent')
            return original_import(name, *args, **kwargs)

        settings = {'IITK_EMBED_URL': 'https://example.invalid/embeddings',
                    'IITK_EMBED_KEY': 'test', 'RAG_RERANKER_ENABLED': 'false'}
        with patch.dict(os.environ, settings), patch('builtins.__import__', side_effect=import_without_local_models):
            retrieval = runpy.run_path(str(agent_bridge.P4_ROOT/'p3_retrieval'/'retrieve.py'))
            retrieval['_load_models']()
            with self.assertRaisesRegex(RuntimeError, 'requirements-local-models.txt'):
                retrieval['_local_model_classes']()

    def test_explicit_external_layout_is_checked_relative_to_its_own_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for relative in ('retrieve.py','index/bm25.pkl','index/faiss.index','index/chunk_ids.json'):
                file=root/relative
                file.parent.mkdir(exist_ok=True)
                file.touch()
            with patch.dict(os.environ,{'P3_RAG_PATH':directory,'LLM_BASE_URL':''}):
                self.assertEqual(agent_bridge.rag_path(),root.resolve())
                self.assertIn('parsed/all_chunks.jsonl',agent_bridge.missing_setup())
                (root/'parsed').mkdir()
                (root/'parsed/all_chunks.jsonl').touch()
                self.assertNotIn('parsed/all_chunks.jsonl',agent_bridge.missing_setup())


if __name__=='__main__': unittest.main()
