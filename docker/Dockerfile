FROM python:3.12-slim
WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Which sub-project to package, e.g. rate_limiters/algorithms/05_gcra
ARG PROJECT
COPY ${PROJECT}/app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
