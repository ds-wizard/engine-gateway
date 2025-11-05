#!/usr/bin/env sh

uvicorn 'engine_gateway:create_app' --reload
