.PHONY: test package server-build server-up server-down client-install

test:
	cd server && python3 -m pytest -q

package:
	python3 scripts/package-kodi-addon.py

client-install:
	pip install -e clients/python

server-build:
	cd server && docker build -t subfly-server:1.0.0 .

server-up:
	cd server && docker compose up -d --build

server-down:
	cd server && docker compose down
