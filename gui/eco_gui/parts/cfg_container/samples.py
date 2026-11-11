SAMPLES = [
    {"name": "今の作り方で動いている", "props": {
        "recipe": {"module": "calc", "environment": "ecobuild-env-calc:d02b6c1e", "image": "ecobuild-calc:50508f81", "context": "C:/work/Calc/.ecobuild/container"},
        "status": {"container": True, "state": "running", "image": "ecobuild-calc:50508f81", "custom_image": "", "outdated": False},
        "images": {"images": [
            {"name": "ecobuild-calc:50508f81", "module": "calc", "size": "1.56GB", "created": "15 minutes ago", "current": True, "used_by": ["C:/work/Calc"], "environment": False},
            {"name": "ecobuild-env-calc:d02b6c1e", "module": "calc", "size": "1.21GB", "created": "2 days ago", "current": True, "used_by": [], "environment": True},
            {"name": "ecobuild-calc:11aa22bb", "module": "calc", "size": "1.52GB", "created": "3 weeks ago", "current": False, "used_by": [], "environment": False},
            {"name": "ecobuild-other:99887766", "module": "other", "size": "2.0GB", "created": "1 month ago", "current": True, "used_by": [], "environment": False}]}}},
    {"name": "古いイメージ・ひな型のまま", "props": {
        "recipe": {"module": "calc", "environment": "ecobuild-env-calc:d02b6c1e", "image": "ecobuild-calc:50508f81", "context": ""},
        "status": {"container": True, "state": "exited", "image": "ecobuild-calc:11aa22bb", "custom_image": "", "outdated": True},
        "images": {"images": []}}},
    {"name": "コンテナにしていない", "props": {
        "recipe": {"module": "calc", "environment": "ecobuild-env-calc:d02b6c1e", "image": "ecobuild-calc:50508f81", "context": "C:/work/Calc/.ecobuild/container"},
        "status": {"container": False, "state": "none", "image": "", "custom_image": "", "outdated": False}}},
    {"name": "読み込み中", "props": {}},
    {"name": "誤り", "props": {"error": "Docker に聞けません"}},
]
