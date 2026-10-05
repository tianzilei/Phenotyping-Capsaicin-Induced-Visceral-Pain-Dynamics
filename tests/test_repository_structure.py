"""Synthetic cases distinguish unpublished artifacts and prose from data literals."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from verify_repository_structure import artifact_issue, comment_issues


class RepositoryStructureTests(unittest.TestCase):
    def test_unpublished_documents_and_plans_rejected(self):
        for name in [
            "MANUSCRIPT.md",
            "supplementary_latest.md",
            "drafts/paper.md",
            "docs/manuscripts/current.md",
            "submission/story.json",
            "config/manuscript_variable_length_v1.json",
            "paper.docx",
            "paper.tex",
            "paper_draft.md",
            "article.html",
        ]:
            self.assertIsNotNone(artifact_issue(name), name)
        for name in ["docs/analysis_plan.md", "config/analysis.json", "README.md"]:
            self.assertIsNone(artifact_issue(name))

    def test_python_comments_and_docstrings_checked(self):
        phrase = "\u6d4b\u8bd5"
        for text in [
            "# " + phrase,
            '"""' + phrase + '"""',
            'def f():\n    """' + phrase + '"""\n',
        ]:
            self.assertTrue(comment_issues("example.py", text))
        self.assertFalse(
            comment_issues("example.py", 'name = "' + phrase + '" # Source label\n')
        )

    def test_r_inline_comments_checked_without_reading_data_as_comments(self):
        phrase = "\u6d4b\u8bd5"
        self.assertTrue(comment_issues("example.R", "x <- 1 # " + phrase + "\n"))
        self.assertFalse(
            comment_issues("example.R", 'x <- "# ' + phrase + '" # Source label\n')
        )
        self.assertFalse(
            comment_issues(
                "example.R", 'x <- r"--(# ' + phrase + '" \n)--" # Source label\n'
            )
        )
        self.assertTrue(
            comment_issues("example.R", 'x <- "escaped\\"# literal" # ' + phrase + "\n")
        )


if __name__ == "__main__":
    unittest.main()
