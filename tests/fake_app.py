import fastapi


def create_app() -> fastapi.FastAPI:
    app = fastapi.FastAPI()

    @app.get('/projects/{project_uuid}/fail')
    def fail(project_uuid: str):
        raise RuntimeError(f'Failed for {project_uuid}')

    @app.get('/ok')
    def ok():
        return {'ok': True}

    return app
