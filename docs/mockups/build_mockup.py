"""Inject mock_data.json into mockup_template.html -> scorecard_explorer_mockup.html"""
from pathlib import Path
here = Path(__file__).parent
data = (here / "mock_data.json").read_text().replace("</", "<\\/")
(here / "scorecard_explorer_mockup.html").write_text((here / "mockup_template.html").read_text().replace("/*DATA*/", data))
