"""資料處理引擎：依 recipe 執行 Load、Gate、Normalize、Match、Transform、Validate、Mapping、Export。

recipe 只描述「要做什麼」，不含任何會被執行的 Python。SQL 片段在 DuckDB 沙箱裡執行，
碰不到檔案、網路或擴充套件。
"""
from .recipe import Recipe, RecipeError, load_recipe  # noqa: F401
from .pipeline import run  # noqa: F401
