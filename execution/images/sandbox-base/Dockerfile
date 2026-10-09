# Base image for task sandboxes (P1). Keep it small; browser variant adds Playwright + Xvfb.
FROM python:3.12-slim
RUN useradd -m -u 10001 agent && mkdir /workspace && chown agent /workspace
USER agent
WORKDIR /workspace
CMD ["sleep", "infinity"]
