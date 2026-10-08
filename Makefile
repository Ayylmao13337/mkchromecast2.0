.PHONY: test build tray clean

test:
	python3 -m unittest discover -s tests

build:
	python3 -m build

tray:
	python3 -m mkchromecast --tray

clean:
	rm -rf build dist
