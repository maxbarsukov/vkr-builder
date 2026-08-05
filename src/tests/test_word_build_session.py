from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from vkr.pagination import WordBuildSession, open_word_build_session


def test_open_word_build_session_factory():
    with patch("vkr.pagination.WordApplicationHost") as host_cls:
        host_cls.return_value.doc = None
        session = open_word_build_session()
        assert isinstance(session, WordBuildSession)
        host_cls.assert_called_once_with(purpose="build")


def test_load_document_refreshes_table_cache():
    with patch("vkr.pagination.WordApplicationHost") as host_cls:
        mock_app = MagicMock()
        mock_doc = MagicMock()
        mock_app.doc = mock_doc
        host_cls.return_value = mock_app
        mock_app.open_document.return_value = mock_doc

        with patch("vkr.pagination.iter_content_tables", return_value=["t1", "t2"]):
            session = WordBuildSession()
            session.load_document("a.docx")
            assert session.fragment_count() == 2
            session.load_document("b.docx")
            assert session.fragment_count() == 2
            assert mock_app.open_document.call_count == 2
            mock_app.open_document.assert_called_with(
                os.path.abspath("b.docx"), repaginate=True
            )

        session.close()
        mock_app.close.assert_called_once()


def test_context_manager_closes_session():
    with patch("vkr.pagination.WordApplicationHost") as host_cls:
        mock_app = MagicMock()
        host_cls.return_value = mock_app
        with WordBuildSession() as session:
            assert session is not None
        mock_app.close.assert_called_once()
