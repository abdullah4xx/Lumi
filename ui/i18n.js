(() => {
  const translations = {
    "Close Lumi": "إغلاق Lumi",
    "Switch to dark mode": "التبديل إلى الوضع الداكن",
    "Switch to light mode": "التبديل إلى الوضع الفاتح",
    "Open Gemini assistant": "فتح مساعد Gemini",
    "Close Gemini assistant": "إغلاق مساعد Gemini",
    "Gemini wallpaper assistant": "مساعد خلفيات Gemini",
    "Gemini wallpaper search": "البحث عن خلفية عبر Gemini",
    "Describe a scene and Lumi will find matching wallpapers.": "صف المشهد الذي تريده وسيبحث Lumi عن خلفيات مناسبة.",
    "Try “a quiet Japanese garden at dusk” or describe your idea in Arabic.": "جرّب «حديقة يابانية هادئة وقت الغروب» أو اكتب وصفك بالعربية.",
    "Describe the wallpaper you want": "اكتب وصف الخلفية التي تريدها",
    "Describe the wallpaper you want…": "اكتب وصف الخلفية التي تريدها…",
    "Search with Gemini": "البحث باستخدام Gemini",
    "Set up Gemini API key in Settings": "أضف مفتاح Gemini API من الإعدادات",
    "Finding wallpapers…": "جارٍ البحث عن الخلفيات…",
    "No matching wallpapers found. Try changing the description.": "لم نعثر على خلفيات مطابقة. جرّب تغيير الوصف.",
    "Could not connect to Lumi: ": "تعذر الاتصال بـ Lumi: ",
    "Could not load wallpapers: ": "تعذر تحميل الخلفيات: ",
    "Could not load more wallpapers: ": "تعذر تحميل المزيد من الخلفيات: ",
    "Could not save settings: ": "تعذر حفظ الإعدادات: ",
    "Live wallpapers need Lumi's local API. Run “PYTHONPATH=src python3 -m lumi --web-server --port 5910”, then open http://127.0.0.1:5910/ (preview returned ": "تحتاج الخلفيات المباشرة إلى واجهة Lumi المحلية. شغّل “PYTHONPATH=src python3 -m lumi --web-server --port 5910”، ثم افتح http://127.0.0.1:5910/ (أعادت المعاينة ",
    "Settings": "الإعدادات",
    "Open settings": "فتح الإعدادات",
    "Close settings": "إغلاق الإعدادات",
    "About Lumi": "حول Lumi",
    "Settings sections": "أقسام الإعدادات",
    "Lumi settings": "إعدادات Lumi",
    "General": "عام",
    "Sources": "المصادر",
    "Gemini": "Gemini",
    "Automation": "الأتمتة",
    "Storage": "التخزين",
    "Appearance": "المظهر",
    "Theme": "السمة",
    "Choose how Lumi looks": "اختر مظهر Lumi",
    "Dark": "داكن",
    "Light": "فاتح",
    "Follow system": "حسب النظام",
    "Language": "اللغة",
    "English": "الإنجليزية",
    "Arabic": "العربية",
    "Adaptive colours": "ألوان متكيفة",
    "Tint the interface with colours from the current wallpaper": "لوّن الواجهة بألوان الخلفية الحالية",
    "Sync system accent": "مزامنة لون النظام",
    "Use the wallpaper palette as the GNOME accent colour": "استخدم ألوان الخلفية كلون تمييز في GNOME",
    "Wallpaper behaviour": "سلوك الخلفيات",
    "Apply wallpaper to": "تطبيق الخلفية على",
    "Desktop and lock screen": "سطح المكتب وشاشة القفل",
    "Desktop": "سطح المكتب",
    "Lock screen": "شاشة القفل",
    "Picture style": "نمط الصورة",
    "Zoom": "تكبير",
    "Scaled": "ملاءمة",
    "Stretched": "تمديد",
    "Centered": "توسيط",
    "Spanned": "امتداد",
    "Tile": "تكرار",
    "Automatic rotation": "تغيير تلقائي للخلفية",
    "Change wallpaper automatically": "تغيير الخلفية تلقائيًا",
    "Rotation interval": "مدة التغيير",
    "Separate dark-mode wallpaper": "خلفية مستقلة للوضع الداكن",
    "Battery saver": "توفير البطارية",
    "Wallpaper sources": "مصادر الخلفيات",
    "Enable or disable wallpaper providers": "تفعيل مصادر الخلفيات أو إيقافها",
    "API key required": "مفتاح API مطلوب",
    "API key": "مفتاح API",
    "Client ID": "معرّف العميل",
    "Client secret": "السرّ",
    "Saved — replace to change": "تم الحفظ — أدخل قيمة جديدة للتغيير",
    "Enabled": "مفعّل",
    "Disabled": "متوقف",
    "Gemini analysis": "تحليل Gemini",
    "Choose Gemini or a local analysis engine. Gemini sends the selected wallpaper to Google and may use your API quota.": "اختر Gemini أو محرك تحليل محلي. يرسل Gemini الخلفية المحددة إلى Google وقد يستهلك حصة API.",
    "Active engine": "المحرك النشط",
    "Depends on the selected engine and installed components": "يعتمد على المحرك المحدد والمكونات المثبتة",
    "Automatic": "تلقائي",
    "Gemini API key": "مفتاح Gemini API",
    "Gemini model": "نموذج Gemini",
    "Gemini 2.5 Flash": "Gemini 2.5 Flash",
    "Gemini 2.5 Pro": "Gemini 2.5 Pro",
    "Gemini 2.0 Flash": "Gemini 2.0 Flash",
    "Loading Gemini models…": "جارٍ تحميل نماذج Gemini…",
    "Gemini models loaded.": "تم تحميل نماذج Gemini.",
    "No Gemini models are available for this API key.": "لا توجد نماذج Gemini متاحة لمفتاح API هذا.",
    "Could not load Gemini models. Check API key.": "تعذر تحميل نماذج Gemini. تحقق من مفتاح API.",
    "Could not save Gemini model.": "تعذر حفظ نموذج Gemini.",
    "Show": "إظهار",
    "Hide": "إخفاء",
    "Show Gemini API key": "إظهار مفتاح Gemini API",
    "Hide Gemini API key": "إخفاء مفتاح Gemini API",
    "Test Gemini connection": "اختبار اتصال Gemini",
    "Test connection": "اختبار الاتصال",
    "Checking Gemini connection…": "جارٍ اختبار اتصال Gemini…",
    "Gemini connection successful.": "تم الاتصال بـ Gemini بنجاح.",
    "Add a Gemini API key before testing.": "أضف مفتاح Gemini API قبل الاختبار.",
    "Gemini API key is invalid.": "مفتاح Gemini API غير صالح.",
    "Gemini API key does not have permission for this model.": "لا يملك مفتاح Gemini API صلاحية استخدام هذا النموذج.",
    "Gemini quota exceeded. Check your Google AI Studio quota.": "تم تجاوز حصة Gemini. تحقق من حصتك في Google AI Studio.",
    "Gemini is rate limited right now. Please try again later.": "طلبات Gemini محدودة حاليًا. حاول مرة أخرى لاحقًا.",
    "Gemini took too long to respond. Please try again.": "استغرق Gemini وقتًا طويلًا للرد. حاول مرة أخرى.",
    "Selected Gemini model was not found.": "لم يتم العثور على نموذج Gemini المحدد.",
    "Could not reach Gemini. Check your network connection.": "تعذر الوصول إلى Gemini. تحقق من اتصال الشبكة.",
    "Could not test Gemini connection.": "تعذر اختبار اتصال Gemini.",
    "Wallpaper results will appear here.": "ستظهر الخلفيات هنا.",
    "Check your connection or add a local folder in Settings.": "تحقق من اتصالك أو أضف مجلدًا محليًا من الإعدادات.",
    "Connect to the internet or add a local folder in Settings.": "اتصل بالإنترنت أو أضف مجلدًا محليًا من الإعدادات.",
    "Used only when Gemini is selected as the analysis engine.": "يُستخدم فقط عند اختيار Gemini كمحرك للتحليل.",
    "Analysis engine": "محرك التحليل",
    "CLIP only": "CLIP فقط",
    "Lightweight only": "المحرك الخفيف فقط",
    "Strict category filter": "تصفية دقيقة حسب التصنيف",
    "Hide images the classifier places in another category": "إخفاء الصور التي يصنفها المحرك ضمن فئة أخرى",
    "AI settings": "إعدادات الذكاء الاصطناعي",
    "Storage settings": "إعدادات التخزين",
    "Clear cache": "مسح ذاكرة التخزين المؤقت",
    "Clear downloads": "مسح التنزيلات",
    "Import images": "استيراد الصور",
    "Add folder": "إضافة مجلد",
    "Choose an option": "اختر خيارًا",
    "Options": "الخيارات",
    "Search wallpapers": "البحث عن خلفيات",
    "Find a wallpaper": "ابحث عن خلفية",
    "Clear search": "مسح البحث",
    "No favourite wallpapers": "لا توجد خلفيات مفضلة",
    "Add a wallpaper to favourites to see it here.": "أضف خلفية إلى المفضلة لتظهر هنا.",
    "No local wallpapers": "لا توجد خلفيات محلية",
    "Import images or add a device folder in Settings.": "استورد صورًا أو أضف مجلدًا من الإعدادات.",
    "No wallpapers found": "لم يتم العثور على خلفيات",
    "Try another category or search term.": "جرّب تصنيفًا أو عبارة بحث أخرى.",
    "Loading wallpapers…": "جارٍ تحميل الخلفيات…",
    "Remove favourite": "إزالة من المفضلة",
    "Add to favourites": "إضافة إلى المفضلة",
    "Added to favourites.": "أُضيفت إلى المفضلة.",
    "Removed from favourites.": "أُزيلت من المفضلة.",
    "Close": "إغلاق",
    "Save": "حفظ",
    "Cancel": "إلغاء",
    "Wallpaper": "خلفية",
    "Favourites": "المفضلة",
    "Local": "محلي",
    "Nature": "الطبيعة",
    "Discover": "استكشاف",
    "Islamic art": "فن إسلامي",
    "Landscape only": "المناظر الطبيعية فقط",
    "Verified sizes only": "الأحجام الموثقة فقط",
    "Safe search": "البحث الآمن",
    "Filter real people": "تصفية صور الأشخاص الحقيقيين",
    "Filter non-Islamic religious imagery": "تصفية الصور الدينية غير الإسلامية",
    "Dock blur": "تمويه الشريط",
    "Update checks are available in the desktop app.": "يتوفر التحقق من التحديثات في تطبيق سطح المكتب.",
    "Checking GitHub for updates…": "جارٍ التحقق من التحديثات على GitHub…",
    "Check for updates": "التحقق من وجود تحديثات",
    "Download update": "تنزيل التحديث",
    "Install update": "تثبيت التحديث",
    "Enabled — experimental": "مفعّل — تجريبي",
    "Website only — no supported public API": "الموقع فقط — لا تتوفر واجهة API عامة مدعومة",
    "Close": "إغلاق",
    "Cancel": "إلغاء",
    "Save": "حفظ",
    "Remove": "إزالة",
    "Add domain": "إضافة نطاق",
    "Add URL": "إضافة رابط",
    "Open folder": "فتح المجلد",
    "Export": "تصدير",
    "Import": "استيراد",
    "Set wallpaper": "تعيين الخلفية",
    "Save image": "حفظ الصورة",
    "Identify category": "تحديد التصنيف",
    "Previous": "السابق",
    "Next": "التالي",
    "Anime wallpapers": "خلفيات أنمي",
    "Cyberpunk wallpapers": "خلفيات سايبربانك",
    "Game wallpapers": "خلفيات ألعاب",
    "Minimalist and clear wallpapers": "خلفيات بسيطة وصافية",
    "Space wallpapers": "خلفيات فضاء",
    "Favourite wallpapers": "الخلفيات المفضلة",
    "Wallpapers on this device": "خلفيات هذا الجهاز",
    "Wallpaper actions": "إجراءات الخلفية",
    "Set a wallpaper": "تعيين خلفية",
    "Save wallpaper": "حفظ الخلفية",
    "Search": "بحث",
    "General settings": "الإعدادات العامة",
    "Personalize Lumi and the way wallpapers appear.": "خصّص Lumi وطريقة عرض الخلفيات.",
    "Personalize Lumi": "تخصيص Lumi",
    "Wallpaper": "الخلفية",
    "Quality & filtering": "الجودة والتصفية",
    "Applied to subsequent searches.": "تُطبّق على عمليات البحث التالية.",
    "Minimum image size": "الحد الأدنى لحجم الصورة",
    "3840 pixels equals 4K": "3840 بكسل تساوي دقة 4K",
    "Hide portrait images": "إخفاء الصور العمودية",
    "Hide images with unknown dimensions until downloaded": "إخفاء الصور مجهولة الأبعاد حتى تنزيلها",
    "Skip Reddit posts flagged 18+": "تجاوز منشورات Reddit المصنفة +18",
    "Blocked websites": "مواقع محظورة",
    "Hide results from specific domains or URLs.": "إخفاء النتائج من نطاقات أو روابط محددة.",
    "Domain to block": "النطاق المطلوب حظره",
    "Custom web sources": "مصادر ويب مخصصة",
    "Add a page that contains wallpapers.": "أضف صفحة تحتوي على خلفيات.",
    "Custom source URL": "رابط المصدر المخصص",
    "No custom URLs added.": "لم تتم إضافة روابط مخصصة.",
    "Local folders": "مجلدات محلية",
    "Browse wallpapers stored on your device.": "تصفّح الخلفيات المخزنة على جهازك.",
    "No folders added.": "لم تتم إضافة مجلدات.",
    "Available sources": "المصادر المتاحة",
    "Enable sources to include them in wallpaper searches. Experimental sources use unofficial feeds and may occasionally fail.": "فعّل المصادر لإضافتها إلى البحث عن الخلفيات. تستخدم المصادر التجريبية موجزات غير رسمية وقد تتعطل أحيانًا.",
    "Custom Python scrapers": "سكربتات Python مخصصة",
    "Add a .py file that defines SOURCE_NAME, SOURCE_URL and search(query, category, page). Python code runs with your user permissions; install files only from sources you trust.": "أضف ملف .py يعرّف SOURCE_NAME وSOURCE_URL والدالة search(query, category, page). يعمل كود Python بصلاحيات المستخدم؛ أضف الملفات من مصادر تثق بها فقط.",
    "Python scraper file": "ملف scraper بصيغة Python",
    "Add scraper": "إضافة scraper",
    "Choose a .py file first.": "اختر ملف .py أولاً.",
    "Python scraper code runs with your user permissions. Install only files you trust. Continue?": "يعمل كود scraper بصلاحيات المستخدم. أضف الملفات التي تثق بها فقط. هل تريد المتابعة؟",
    "Checking and loading scraper…": "جارٍ التحقق من scraper وتحميله…",
    "API keys": "مفاتيح API",
    "Manage credentials for wallpaper sources.": "إدارة بيانات اعتماد مصادر الخلفيات.",
    "Reddit": "Reddit",
    "Subreddits to browse, separated by commas.": "مجتمعات Reddit للتصفح، مفصولة بفواصل.",
    "Display & rotation": "العرض والتغيير",
    "Rendering resolution": "دقة العرض",
    "Maximum pixels drawn by the carousel; higher values can use more memory.": "أقصى عدد بكسلات يرسمها المعرض؛ القيم الأعلى قد تستهلك ذاكرة أكثر.",
    "4 million pixels": "4 ملايين بكسل",
    "8 million pixels": "8 ملايين بكسل",
    "12 million pixels": "12 مليون بكسل",
    "Background blur": "تمويه الخلفية",
    "Adjust the blur behind the wallpaper; clarity is prioritized by default": "اضبط التمويه خلف الخلفية؛ الوضوح هو الخيار الافتراضي",
    "Settings window blur": "تمويه نافذة الإعدادات",
    "Adjust the frosted glass strength": "اضبط قوة الزجاج المصنفر",
    "Soften the wallpaper behind the category dock": "نعّم الخلفية خلف شريط التصنيفات",
    "Pause the carousel from changing on its own": "أوقف التغيير التلقائي للصور",
    "Change every": "التغيير كل",
    "From 2 to 60 seconds": "من ثانيتين إلى 60 ثانية",
    "Day & night": "النهار والليل",
    "Use a different image for day and night": "استخدم صورة مختلفة للنهار والليل",
    "Performance & effects": "الأداء والتأثيرات",
    "Reduce background work to save power": "قلّل المهام في الخلفية لتوفير الطاقة",
    "Downloads & cache": "التنزيلات وذاكرة التخزين",
    "Thumbnail cache": "ذاكرة الصور المصغرة",
    "Temporary files used to load previews faster": "ملفات مؤقتة لتسريع تحميل المعاينات",
    "Downloaded wallpapers": "الخلفيات المنزّلة",
    "The folder used by the app": "المجلد الذي يستخدمه التطبيق",
    "Backup": "نسخة احتياطية",
    "Keep a copy of your preferences and move them to another device.": "احتفظ بنسخة من تفضيلاتك وانقلها إلى جهاز آخر.",
    "Settings & favourites": "الإعدادات والمفضلة",
    "Version": "الإصدار",
    "Updates": "التحديثات",
    "Check for a newer version": "تحقق من وجود إصدار أحدث",
    "Release": "الإصدار المنشور",
    "Developer": "المطوّر",
    "Open GitHub releases": "فتح إصدارات GitHub",
    "Open Lumi on GitHub": "فتح Lumi على GitHub",
    "Enter an HTTP or HTTPS URL.": "أدخل رابط HTTP أو HTTPS.",
    "Use an HTTP or HTTPS URL.": "استخدم رابط HTTP أو HTTPS.",
    "Folder selection is available in the Lumi desktop app.": "اختيار المجلدات متاح في تطبيق Lumi لسطح المكتب.",
    "Image import is available in the Lumi desktop app.": "استيراد الصور متاح في تطبيق Lumi لسطح المكتب.",
    "Set wallpaper": "تعيين الخلفية",
    "Wallpaper set.": "تم تعيين الخلفية.",
    "Setting wallpaper…": "جارٍ تعيين الخلفية…",
    "Saving wallpaper…": "جارٍ حفظ الخلفية…",
    "Analysing wallpaper on this device…": "جارٍ تحليل الخلفية على هذا الجهاز…",
    "Local folder added.": "تمت إضافة المجلد المحلي.",
    "Settings and favourites restored. Restart the gallery to refresh its settings.": "تمت استعادة الإعدادات والمفضلة. أعد تشغيل المعرض لتحديث الإعدادات.",
    "Search results": "نتائج البحث",
    "Manage image sources and their connections.": "إدارة مصادر الصور والاتصال بها.",
    "Set up Gemini analysis and choose how wallpapers are classified.": "إعداد تحليل Gemini واختيار طريقة تصنيف الخلفيات.",
    "Configure wallpaper rotation and display effects.": "ضبط تغيير الخلفيات وتأثيرات العرض.",
    "Manage downloaded images and backup your settings.": "إدارة الصور المنزّلة والنسخ الاحتياطي للإعدادات.",
    "Set up wallpaper rotation and background tasks.": "إعداد تغيير الخلفيات والمهام في الخلفية.",
    "Storage & backup": "التخزين والنسخ الاحتياطي",
    "Review downloads, cache, and backup options.": "مراجعة التنزيلات وذاكرة التخزين وخيارات النسخ الاحتياطي.",
    "Wallpaper sources": "مصادر الخلفيات",
    "Clear cache": "مسح ذاكرة التخزين",
    "Clear downloads": "مسح التنزيلات",
    "Domain to block": "النطاق المطلوب حظره",
    "Wallpaper actions": "إجراءات الخلفية",
    "Loading wallpapers…": "جارٍ تحميل الخلفيات…",
    "Set wallpaper": "تعيين الخلفية",
    "Save image": "حفظ الصورة",
    "Identify category": "تحديد التصنيف",
    "Anime": "أنمي",
    "Cyberpunk": "سايبربانك",
    "Games": "ألعاب",
    "Minimalist": "بسيط",
    "Space": "الفضاء",
    "Enabled": "مفعّل",
    "Disabled": "متوقف",
    "Experimental — enabled": "تجريبي — مفعّل",
    "Experimental — disabled": "تجريبي — متوقف",
    "Experimental": "تجريبي",
    "Results": "نتائج",
    "No blocked websites.": "لا توجد مواقع محظورة.",
    "No folders added.": "لم تتم إضافة مجلدات.",
    "Open folder": "فتح المجلد",
    "Downloaded image cache cleared": "تم مسح ذاكرة الصور المنزّلة",
    "Thumbnail cache cleared": "تم مسح ذاكرة الصور المصغّرة",
    "Could not set wallpaper: ": "تعذر تعيين الخلفية: ",
    "Could not update favourite: ": "تعذر تحديث المفضلة: ",
    "Could not classify wallpaper: ": "تعذر تصنيف الخلفية: ",
    "Could not import images: ": "تعذر استيراد الصور: ",
    "Could not export backup: ": "تعذر تصدير النسخة الاحتياطية: ",
    "Could not import backup: ": "تعذر استيراد النسخة الاحتياطية: ",
    "Could not read backup: ": "تعذر قراءة النسخة الاحتياطية: ",
    "Detected: ": "التصنيفات المكتشفة: ",
    "Added to favourites.": "أُضيفت إلى المفضلة.",
    "Removed from favourites.": "أُزيلت من المفضلة.",
    "Your wallpaper was set.": "تم تعيين الخلفية.",
    "No matching wallpapers found. Try changing the description.": "لم نعثر على خلفيات مطابقة. جرّب تغيير الوصف.",
    "API key saved — replace to change": "تم حفظ المفتاح — أدخل مفتاحًا آخر للتغيير",
    "Add a Gemini API key in Settings before searching.": "أضف مفتاح Gemini API من الإعدادات قبل البحث.",
    "Enter a wallpaper request under 500 characters.": "اكتب وصفًا للخلفية لا يتجاوز 500 حرف.",
    "Describe the wallpaper you want.": "اكتب وصف الخلفية التي تريدها.",
    "Try another category or search term.": "جرّب تصنيفًا أو عبارة بحث أخرى.",
  };
  const reverseTranslations = new Map(
    Object.entries(translations).map(([english, arabic]) => [arabic, english]),
  );
  const dynamicPrefixes = [
    ["Could not load wallpapers: ", "تعذر تحميل الخلفيات: "],
    ["Could not load more wallpapers: ", "تعذر تحميل المزيد من الخلفيات: "],
    ["Could not save settings: ", "تعذر حفظ الإعدادات: "],
    ["Could not connect to Lumi: ", "تعذر الاتصال بـ Lumi: "],
    ["Could not set wallpaper: ", "تعذر تعيين الخلفية: "],
    ["Could not update favourite: ", "تعذر تحديث المفضلة: "],
    ["Could not classify wallpaper: ", "تعذر تصنيف الخلفية: "],
    ["Could not import images: ", "تعذر استيراد الصور: "],
    ["Could not export backup: ", "تعذر تصدير النسخة الاحتياطية: "],
    ["Could not import backup: ", "تعذر استيراد النسخة الاحتياطية: "],
    ["Could not read backup: ", "تعذر قراءة النسخة الاحتياطية: "],
    ["Detected: ", "التصنيفات المكتشفة: "],
  ];
  const attributeNames = ["aria-label", "aria-description", "title", "placeholder"];
  const sourceText = new WeakMap();
  let language = "en";

  function localize(value) {
    const trimmed = value.trim();
    if (!trimmed) return value;
    let translated = language === "ar"
      ? translations[trimmed]
      : reverseTranslations.get(trimmed);
    if (!translated) {
      for (const [englishPrefix, arabicPrefix] of dynamicPrefixes) {
        const from = language === "ar" ? englishPrefix : arabicPrefix;
        if (!trimmed.startsWith(from)) continue;
        const to = language === "ar" ? arabicPrefix : englishPrefix;
        translated = to + trimmed.slice(from.length);
        break;
      }
    }
    if (!translated && language === "ar" &&
        trimmed.startsWith("Live wallpapers need Lumi's local API.")) {
      translated = "لتشغيل الخلفيات المباشرة، شغّل خادم Lumi المحلي وافتح عنوانه.";
    }
    if (!translated && language === "en" &&
        trimmed.startsWith("لتشغيل الخلفيات المباشرة، شغّل خادم Lumi المحلي")) {
      translated = "Live wallpapers need Lumi's local API. Run “PYTHONPATH=src python3 -m lumi --web-server --port 5910”, then open http://127.0.0.1:5910/.";
    }
    translated ||= trimmed;
    if (translated === trimmed) return value;
    return value.replace(trimmed, translated);
  }

  function translateNode(node) {
    if (node.nodeType === Node.TEXT_NODE) {
      if (!sourceText.has(node)) {
        const existingSource = reverseTranslations.get(node.nodeValue.trim());
        sourceText.set(node, existingSource || node.nodeValue);
      }
      const source = sourceText.get(node);
      const translated = language === "ar" ? localize(source) : source;
      if (translated !== node.nodeValue) node.nodeValue = translated;
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    attributeNames.forEach(name => {
      if (!node.hasAttribute(name)) return;
      const translated = localize(node.getAttribute(name));
      if (translated !== node.getAttribute(name)) node.setAttribute(name, translated);
    });
    if (node.tagName === "OPTION" && !node.dataset.lumiOriginal) {
      node.dataset.lumiOriginal = node.textContent;
    }
    node.childNodes.forEach(translateNode);
  }

  function setLanguage(nextLanguage) {
    language = nextLanguage === "ar" ? "ar" : "en";
    document.documentElement.lang = language;
    document.documentElement.dir = language === "ar" ? "rtl" : "ltr";
    document.body.classList.toggle("is-arabic", language === "ar");
    translateNode(document.body);
  }

  function getSourceText(element) {
    if (!element) return "";
    return [...element.childNodes].map(node => {
      if (node.nodeType === Node.TEXT_NODE) return sourceText.get(node) || node.nodeValue;
      return node.nodeType === Node.ELEMENT_NODE ? getSourceText(node) : "";
    }).join("").trim();
  }

  new MutationObserver(records => {
    records.forEach(record => {
      if (record.type === "characterData") translateNode(record.target);
      else record.addedNodes.forEach(translateNode);
      if (record.type === "attributes") translateNode(record.target);
    });
  }).observe(document.body, {
    subtree: true,
    childList: true,
    characterData: true,
    attributes: true,
    attributeFilter: attributeNames,
  });

  window.LumiI18n = { setLanguage, getSourceText, translate: localize };
})();
