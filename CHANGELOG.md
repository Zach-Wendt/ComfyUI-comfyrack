# Changelog

All notable changes to the ComfyUI-comfyrack pack. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.1.0] - 2026-10-01

### Added

- First public release.
- `GET /comfyrack/info` and `GET /comfyrack/outputs`: read-only routes that list this ComfyUI's output files
  for comfyrack and Superflow.
- A "Share this ComfyUI on my tailnet" setting that makes this ComfyUI reachable from your other machines over
  Tailscale. It only accepts requests from the same machine.
