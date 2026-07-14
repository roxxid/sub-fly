.PHONY: test package server-build server-up server-down client-install android-build android-lint

test:
	cd server && python3 -m pytest -q
	cd clients/kodi && python3 -m pytest -q tests/
	cd clients/python && PYTHONPATH=. python3 -m pytest -q

package:
	python3 scripts/package-kodi-addon.py

client-install:
	pip install -e clients/python

android-build:
	cd clients/android && ./gradlew assembleDebug

android-lint:
	cd clients/android && ./gradlew lintDebug

server-build:
	cd server && docker build -t subfly-server:1.0.0 .

server-up:
	cd server && docker compose up -d --build

server-down:
	cd server && docker compose down
