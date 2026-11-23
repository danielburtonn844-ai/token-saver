.PHONY: help test smoke bench calib lint build install uninstall clean

help:
	@sed -n '1,20p' Makefile | sed -n 's/^# \{0,1\}//p'

test:            ## 单元测试（零依赖）
	python3 -m unittest discover -s tests -t . -v

smoke:           ## 安装/卸载闭环冒烟
	bash tests/smoke.sh

bench:           ## 生成 bench/RESULTS.md
	python3 bench/bench.py

calib:           ## 重新校准 token 系数（需要 tiktoken）
	python3 bench/calibrate.py

lint:
	python3 -m ruff check .

build:
	python3 -m build

install:         ## 装技能到自动探测的目标
	bash scripts/install.sh --target auto

uninstall:
	bash scripts/install.sh --target auto --uninstall

clean:
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
