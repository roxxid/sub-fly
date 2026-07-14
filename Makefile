.PHONY: test package server-build server-up server-down client-install android-build android-lint android-install android-deploy android-connect

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

# Usage: make android-connect STICK=192.168.1.50 (or STICK=192.168.1.50:5555)
android-connect:
	@if [ -z "$(STICK)" ]; then echo "Usage: make android-connect STICK=<ip>[:port]"; exit 1; fi
	@case "$(STICK)" in \
		*:*) adb connect "$(STICK)" ;; \
		*) adb connect "$(STICK):5555" ;; \
	esac

# Installs the debug APK on whichever device(s) adb currently sees (USB or
# already `adb connect`-ed over network). Add -s <serial> yourself via
# ADB_ARGS if you have multiple devices attached.
android-install:
	adb $(ADB_ARGS) install -r clients/android/app/build/outputs/apk/debug/app-debug.apk

# Build + (optionally connect over network) + install + launch in one step.
# Usage: make android-deploy [STICK=192.168.1.50]
android-deploy: android-build
	@if [ -n "$(STICK)" ]; then $(MAKE) android-connect STICK=$(STICK); fi
	$(MAKE) android-install
	adb $(ADB_ARGS) shell am start -n com.subfly.captions/.MainActivity

server-build:
	cd server && docker build -t subfly-server:1.0.0 .

server-up:
	cd server && docker compose up -d --build

server-down:
	cd server && docker compose down
