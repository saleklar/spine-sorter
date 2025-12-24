from spine_file_sorter_single import run_headless

if __name__ == '__main__':
    run_headless(
        spine_exe=r'C:\Program Files\Spine\Spine.exe',
        spine_project=r'Z:\lucky chanrs trio\Spine\symbols_v6.spine',
        out=r'Z:\spine sorter v257\output',
        import_version=None,
        no_import=False,
        dry=False,
        write_fixed=True,
        launch=False,
        log_callback=print,
    )
