# ai-video-orchestra

Первая рабочая часть локального пайплайна: запуск API-workflow Wan 2.2 TI2V-5B в
ComfyUI, ожидание результата и сохранение видео вместе с диагностическими
артефактами задачи.

## Что уже работает

- `doctor` проверяет Python, ComfyUI и структуру workflow;
- `inspect-workflow` показывает все узлы и выделяет узлы, которые меняет генератор;
- `generate` подставляет параметры, отправляет workflow в ComfyUI, следит за своей
  задачей по WebSocket и скачивает результат;
- каждая задача сохраняет запрос, отправленный workflow, статус, лог и `scene.mp4`;
- исходный workflow никогда не перезаписывается.

## Первый запуск на Windows

Требуются Python 3.11 и уже настроенный ComfyUI, доступный по адресу
`http://127.0.0.1:8188`.

```powershell
git clone https://github.com/maggogerka/ai-video-orchestra.git
cd ai-video-orchestra
Copy-Item .env.example .env
Copy-Item "путь-к-вашему-workflow.json" workflows/wan22_5b_t2v_api.json
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
powershell -ExecutionPolicy Bypass -File scripts/doctor.ps1
.\.venv\Scripts\python.exe -m video_orchestra inspect-workflow workflows/wan22_5b_t2v_api.json
powershell -ExecutionPolicy Bypass -File scripts/generate_test.ps1
```

Workflow нужно экспортировать из ComfyUI именно в **API format**, а не обычной
кнопкой сохранения интерфейсного workflow. В настройках ComfyUI включите Dev Mode,
затем используйте `Save (API Format)`.

## Команды

```powershell
.\.venv\Scripts\python.exe -m video_orchestra doctor
.\.venv\Scripts\python.exe -m video_orchestra inspect-workflow workflows/wan22_5b_t2v_api.json
.\.venv\Scripts\python.exe -m video_orchestra generate `
  --prompt "A cinematic aerial shot of a lighthouse during a storm" `
  --negative "blurry, low quality" `
  --width 480 --height 832 --frames 81 --fps 16 `
  --steps 20 --cfg 5
```

Полный список параметров:

```powershell
.\.venv\Scripts\python.exe -m video_orchestra generate --help
```

Параметр `--output` меняет корневой каталог задач. Если `--seed` не задан, он
создаётся случайно. Таймаут по умолчанию — 1800 секунд.

## Результаты и диагностика

Для каждой генерации создаётся отдельная папка:

```text
runs/<job_id>/
├── request.json
├── workflow_submitted.json
├── status.json
├── run.log
└── scene.mp4
```

При ошибке `status.json` содержит этап, тип исключения, текст ошибки и `prompt_id`,
если ComfyUI уже принял задачу. Подробный журнал находится в `run.log`. Журналы
PowerShell-скриптов пишутся в `logs/`.

## Настройки

Настройки читаются из `.env`:

```dotenv
COMFY_URL=http://127.0.0.1:8188
COMFY_TIMEOUT_SEC=1800
COMFY_WORKFLOW=workflows/wan22_5b_t2v_api.json
RUNS_DIR=runs
```

Пути относительные, поэтому проект можно перенести на другой ПК целиком. Виртуальное
окружение переносить не следует: скопируйте/клонируйте репозиторий, положите workflow,
скопируйте `.env.example` в `.env` и снова запустите `scripts/bootstrap.ps1`. Скрипт не
устанавливает PyTorch, ComfyUI или модели.

## Разработка

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
```
