// Настройки профиля приставки: применяются при каждом запуске.
// Переводчик выключен: всплывающая панель перекрывает сетку плиток.
user_pref("browser.translations.enable", false);
user_pref("browser.translations.automaticallyPopup", false);
// Профиль киоска: без приветствий, телеметрии и «восстановить сессию»
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("browser.startup.homepage_override.mstone", "ignore");
user_pref("browser.aboutwelcome.enabled", false);
user_pref("datareporting.healthreport.uploadEnabled", false);
user_pref("datareporting.policy.dataSubmissionEnabled", false);
user_pref("toolkit.telemetry.enabled", false);
user_pref("browser.sessionstore.resume_from_crash", false);
user_pref("browser.tabs.warnOnClose", false);
user_pref("browser.fullscreen.autohide", true);
user_pref("browser.newtabpage.enabled", false);
user_pref("browser.startup.homepage", "http://127.0.0.1:8090/");
user_pref("full-screen-api.ignore-widgets", true);
user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);

// Кэш: без предела Firefox разрешает себе до гигабайта на большом диске.
// Гигабайт кэша на медленном диске — это 20–30 секунд до появления окна,
// а всё это время на телевизоре чёрный экран с курсором.
user_pref("browser.cache.disk.smart_size.enabled", false);
user_pref("browser.cache.disk.capacity", 262144);   // 256 МБ
user_pref("browser.cache.memory.capacity", 65536);  // 64 МБ
user_pref("browser.startup.page", 1);

// Менеджер паролей не должен показывать под полем пароля строку
// «Manage Passwords»: на телевизоре она накрывает само поле, и курсором
// до него не добраться (Sonarr, Radarr и прочие локальные службы).
user_pref("signon.showAutoCompleteFooter", false);

// Выпадающая панель автодополнения перекрывает поля ввода на телевизоре
// и перехватывает клики; входы всё равно вводим сами.
user_pref("browser.formfill.enable", false);
user_pref("signon.rememberSignons", false);

// Встроенный канал управления: список вкладок и заполнение форм входа.
// Слушает только 127.0.0.1.
user_pref("marionette.enabled", true);
user_pref("marionette.port", 2828);