.PHONY: test package service-up service-down

test:
	cd service && python3 -m pytest -q

package:
	python3 scripts/package-kodi-addon.py

service-up:
	cd service && docker compose up -d --build

service-down:
	cd service && docker compose down
