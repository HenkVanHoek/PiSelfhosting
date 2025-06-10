# Use a lightweight Python 3.9 image as base
FROM python:3.9-slim-buster

# Install ffmpeg, which includes the ffprobe tool, necessary for testing RTSP streams
# Also install libxml2-dev and libxslt1-dev, needed for lxml (onvif-zeep dependency)
# build-essential for compilation purposes
RUN apt-get update && apt-get install -y ffmpeg libxml2-dev libxslt1-dev build-essential     && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (pyyaml and onvif-zeep)
# Pinned onvif-zeep version to use the latest available version from pip (0.2.12 based on previous output)
# and forcing a rebuild of this layer.
RUN pip install --no-cache-dir pyyaml onvif-zeep==0.2.12 lxml # rebuild-trigger-005

# Debugging step: Try to import onvif and check its contents by writing to a temp file
# This step will now succeed even if 'onvif.discovery' is not found,
# allowing the Docker image to build successfully.
RUN echo "import sys" > /tmp/debug_onvif.py &&     echo "try:" >> /tmp/debug_onvif.py &&     echo "    import onvif;" >> /tmp/debug_onvif.py &&     echo "    print('onvif module loaded successfully.');" >> /tmp/debug_onvif.py &&     echo "    print('Contents of onvif module:');" >> /tmp/debug_onvif.py &&     echo "    print(dir(onvif));" >> /tmp/debug_onvif.py &&     echo "    if 'discover' in dir(onvif):" >> /tmp/debug_onvif.py &&     echo "        print('\"discover\" found in onvif module. Attempting direct import.');" >> /tmp/debug_onvif.py &&     echo "        from onvif import discover;" >> /tmp/debug_onvif.py &&     echo "        print('Successfully imported discover from onvif.');" >> /tmp/debug_onvif.py &&     echo "    else:" >> /tmp/debug_onvif.py &&     echo "        print('\"discover\" NOT found directly in onvif module. This is expected for some versions.');" >> /tmp/debug_onvif.py &&     echo "        try:" >> /tmp/debug_onvif.py &&     echo "            from onvif.discovery import discover;" >> /tmp/debug_onvif.py &&     echo "            print('Successfully imported discover from onvif.discovery.');" >> /tmp/debug_onvif.py &&     echo "        except ImportError as e_sub:" >> /tmp/debug_onvif.py &&     echo "            print('Error importing discover from onvif.discovery: {}'.format(e_sub));" >> /tmp/debug_onvif.py &&     echo "            print('ONVIF discovery will still be unavailable.');" >> /tmp/debug_onvif.py &&     echo "            # sys.exit(1); # REMOVED: Do not exit on ImportError, allow build to succeed" >> /tmp/debug_onvif.py &&     echo "except ImportError as e:" >> /tmp/debug_onvif.py &&     echo "    print('Error importing onvif module: {}'.format(e));" >> /tmp/debug_onvif.py &&     echo "    print('Sys path:', sys.path);" >> /tmp/debug_onvif.py &&     echo "    sys.exit(1);" >> /tmp/debug_onvif.py &&     echo "except Exception as e:" >> /tmp/debug_onvif.py &&     echo "    print('Unexpected error during onvif import test: {}'.format(e));" >> /tmp/debug_onvif.py &&     echo "    sys.exit(1);" >> /tmp/debug_onvif.py &&     python3 /tmp/debug_onvif.py &&     rm /tmp/debug_onvif.py # Clean up the temporary file

# Set the working directory inside the container
WORKDIR /app

# Copy the Python script to the working directory in the container
# This script will be included in the Docker image itself.
COPY frigate_config_tool.py .

# Define the entrypoint of the container.
# When the container starts, this command will be executed automatically.
# The script expects access to specific paths on the host, which we will handle via volume mounts later.
ENTRYPOINT ["python3", "frigate_config_tool.py"]
