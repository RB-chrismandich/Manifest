#!/bin/bash
sed -i 's/^# shellcheck disable=.*/# shellcheck disable=SC2016,SC2059,SC2004,SC2129/' configs/claude/scripts/parallel_agent.sh
