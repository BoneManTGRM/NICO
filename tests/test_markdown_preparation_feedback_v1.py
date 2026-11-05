import subprocess


def test_markdown_preparation_feedback_behavior():
    subprocess.run(['node', '--test', 'tests/js/markdown-preparation-feedback.test.cjs'], check=True)
