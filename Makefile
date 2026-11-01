.PHONY: install demo test
install:
	python -m pip install -r requirements.txt
demo:
	python -m onboarding_sim generate --scale starter
	python -m onboarding_sim validate
	python -m onboarding_sim init-app
	python -m onboarding_sim serve
test:
	pytest -q
