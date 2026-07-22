from app.config import settings

def test_settings_load():
    assert settings.APP_NAME == "MergeLens"
    assert settings.ENVIRONMENT == "development"
    assert settings.DEBUG is True
