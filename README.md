# home-assistant-appdaemon

A repository for Robins Home Assistant AppDaemon apps

**Python venv Setup (Windows)**

Create the virtual environment:

   ```powershell
   python -m venv venv
   ```

Install AppDaemon and dev tools into the venv:
First, activate the environment:

```powershell
.\venv\Scripts\Activate.ps1
```

Then install:

```powershell
pip install appdaemon
```

Using the environment in VS Code:
You do **not** need to activate the venv every time. Just make sure VS Code is using the interpreter from the virtual environment:

* Open the Command Palette: `Ctrl+Shift+P`
* Choose: `Python: Select Interpreter`
* Pick: `.\venv\Scripts\python.exe`

This ensures linting and IntelliSense work correctly.

**Adding Home Assistant Token**

Create a `.env` file in the project root like this:

```dotenv
HASS_TOKEN=your-long-lived-home-assistant-token
```
