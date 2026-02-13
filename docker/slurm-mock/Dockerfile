FROM python:3.11-alpine

# Install bash for scripting
RUN apk add --no-cache bash

WORKDIR /slurm

# Copy mock SLURM binaries
COPY bin/sbatch /usr/local/bin/sbatch
COPY bin/squeue /usr/local/bin/squeue
COPY bin/job_manager.py /slurm/job_manager.py

# Make scripts executable
RUN chmod +x /usr/local/bin/sbatch /usr/local/bin/squeue

# Create job storage directory
RUN mkdir -p /slurm/jobs

# Start job manager daemon
CMD ["python", "/slurm/job_manager.py"]
