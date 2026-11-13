SAMPLES = [
    {"name": "タスクブランチ（書ける・試せる）", "props": {
        "data": {"text": "FROM ubuntu:24.04\nRUN apt-get update\n", "exists": True, "hash": "d02b6c1e", "image": "ecobuild-env-calc:d02b6c1e",
                 "image_ready": True, "outdated": False, "container_image": "", "editable": True, "reason": "",
                 "docker_ready": True, "docker_detail": "Docker 29"},
        "layer": "RUN echo layer\n"}},
    {"name": "既定のブランチ（書けない・Docker もない）", "props": {
        "data": {"text": "FROM ubuntu:24.04\n", "exists": False, "hash": "aa11", "image": "ecobuild-env-calc:aa11",
                 "image_ready": False, "outdated": True, "container_image": "ecobuild-calc:old", "editable": False,
                 "reason": "コンテナの環境（Dockerfile）の変更はタスクブランチ（task/<番号>のブランチ）でだけ行えます。",
                 "docker_ready": False, "docker_detail": "Docker Desktop が動いていません"}}},
    {"name": "読み込み中", "props": {"loading": True}},
    {"name": "誤り", "props": {"error": "作業空間を読めません"}},
]
