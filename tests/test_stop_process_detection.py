import stop


def test_is_aethelgard_process_detects_relative_startpy_with_project_cwd() -> None:
    cmdline = ["python", ".\\start.py"]
    proc_cwd = "C:/Users/Jose Herrera/Documents/Proyectos/Aethelgard"
    marker = "c:/users/jose herrera/documents/proyectos/aethelgard"

    assert stop._is_aethelgard_process(cmdline, proc_cwd, marker)


def test_is_aethelgard_process_rejects_non_project_relative_startpy() -> None:
    cmdline = ["python", ".\\start.py"]
    proc_cwd = "C:/Users/Jose Herrera/Documents/OtroProyecto"
    marker = "c:/users/jose herrera/documents/proyectos/aethelgard"

    assert not stop._is_aethelgard_process(cmdline, proc_cwd, marker)


def test_is_aethelgard_process_accepts_absolute_project_cmdline() -> None:
    cmdline = [
        "C:/Python/python.exe",
        "C:/Users/Jose Herrera/Documents/Proyectos/Aethelgard/start.py",
    ]
    proc_cwd = None
    marker = "c:/users/jose herrera/documents/proyectos/aethelgard"

    assert stop._is_aethelgard_process(cmdline, proc_cwd, marker)
