# FlaskTaskScheduler

A lightweight local task scheduling system built with Flask.

FlaskTaskScheduler provides a browser-based interface for creating, scheduling, and executing Python tasks locally. It is designed for simple automation workflows without relying on cloud services or external schedulers.

## Features

- Web-based task management
- User authentication and role management
- Drag-and-drop weekly scheduling
- 15-minute scheduling intervals
- Background task execution
- Custom Python script execution
- Optional task input parameters
- SQLite-based local storage
- Sleep prevention during runtime

## Requirements

- Python 3.10+
- Flask
- SQLite

## Installation

```bash
git clone https://github.com/AllForABlueRose/FlaskTaskScheduler.git
cd FlaskTaskScheduler
pip install -r requirements.txt
```

## Running

```bash
python app.py
```

Open:

```text
http://localhost:5000
```

## Notes

- Tasks are scheduled in 15-minute intervals.
- The scheduler checks for runnable tasks automatically.
- Tasks are executed using Python `exec()`.

> Only use in trusted local environments.

## License

MIT License
