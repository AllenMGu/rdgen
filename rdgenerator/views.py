import io
from pathlib import Path
import binascii
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.core.files.base import ContentFile
import os
import secrets
import re
import requests
import base64
import json
import uuid
import pyzipper
from django.conf import settings as _settings
from django.db.models import Q
from .custom_config import build_custom_config
from .forms import GenerateForm
from .models import GithubRun
from PIL import Image


PASSTHROUGH_FIELDS = (
    "ui_mode",
    "updateLink",
    "unlockPin",
    "delayFix",
    "cycleMonitor",
    "xOffline",
    "removeNewVersionNotif",
    "hide_chat_voice",
    "hide_sensitive_ui",
    "hideMenuBar",
    "hideQuit",
    "addcopy",
    "applyprivacy",
    "passpolicy",
    "no_uninstall",
    "disable_install",
)


def _public_generator_url(request):
    configured_url = _settings.GENURL.strip().rstrip("/")
    if configured_url:
        if "://" not in configured_url:
            configured_url = f"{_settings.PROTOCOL}://{configured_url}"
        return configured_url
    return f"{_settings.PROTOCOL}://{request.get_host()}"


def _generator_form(request):
    is_json = request.content_type == "application/json"
    if not is_json:
        return GenerateForm(request.POST, request.FILES), False

    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return None, True
    if not isinstance(payload, dict):
        return None, True

    # Saved browser configurations use these names for base64 image data.
    for file_field, base64_field in (
        ("iconfile", "iconbase64"),
        ("logofile", "logobase64"),
        ("privacy_wallpaper", "privacybase64"),
    ):
        value = payload.get(file_field)
        if isinstance(value, str) and value.startswith("data:image/"):
            payload[base64_field] = value
    if payload.get("view_style") is False:
        payload["view_style"] = ""
    if isinstance(payload.get("privacy_wallpaper"), dict):
        payload["privacy_wallpaper"] = ""
    return GenerateForm(payload), True


def _workflow_url(platform, selfhosted):
    workflow = {
        "windows": "sh-generator-windows.yml" if selfhosted else "generator-windows.yml",
        "windows-x86": "generator-windows-x86.yml",
        "linux": "generator-linux.yml",
        "android": "generator-android.yml",
        "macos": "generator-macos.yml",
    }.get(platform, "generator-windows.yml")
    return (
        f"https://api.github.com/repos/{_settings.GHUSER}/{_settings.REPONAME}"
        f"/actions/workflows/{workflow}/dispatches"
    )


def _source_ref(version):
    if _settings.RUSTDESK_REF:
        return _settings.RUSTDESK_REF
    if _settings.RUSTDESK_REPOSITORY != "rustdesk/rustdesk":
        return "master"
    return "master" if version == "master" else f"refs/tags/{version}"


def _server_public_key():
    key_file = _settings.RUSTDESK_PUBLIC_KEY_FILE.strip()
    if not key_file:
        return ""
    try:
        key = Path(key_file).read_text(encoding="utf-8").strip()
        decoded_key = base64.b64decode(key, validate=True)
    except (OSError, ValueError, binascii.Error):
        return ""
    return key if len(decoded_key) == 32 else ""


def generator_view(request):
    if request.method == 'POST':
        form, is_json = _generator_form(request)
        if form is None:
            return JsonResponse({"error": "Request body must be a JSON object"}, status=400)

        if form.is_valid():
            cleaned_data = form.cleaned_data
            user_secret = cleaned_data['sh_secret_field']
            selfhosted = bool(user_secret) and secrets.compare_digest(
                _settings.SH_SECRET, user_secret
            )
            platform = cleaned_data['platform']
            version = cleaned_data['version']
            server = cleaned_data['serverIP']
            key = cleaned_data['RS_PUB_KEY'] or cleaned_data['key']
            apiServer = cleaned_data['apiServer']
            urlLink = cleaned_data['urlLink']
            downloadLink = cleaned_data['downloadLink']
            updateLink = cleaned_data['updateLink']
            if not server:
                server = 'rs-ny.rustdesk.com' #default rustdesk server
            if not key and cleaned_data['serverIP']:
                key = _server_public_key()
            if not key:
                if cleaned_data['serverIP']:
                    form.add_error(
                        'RS_PUB_KEY',
                        'A RustDesk server public key is required for a custom server.',
                    )
                else:
                    key = 'OeVuKk5nlHiXp+APNn0Y3pC1Iwpwn44JGqrQCsWqmBw='
            if not apiServer:
                apiServer = server+":21114"
            if not urlLink:
                urlLink = "https://rustdesk.com"
            if not downloadLink:
                downloadLink = "https://rustdesk.com/download"
            appname = cleaned_data['appname']
            if not appname:
                appname = "rustdesk"
            filename = cleaned_data['exename']
            compname = cleaned_data['compname']
            if not compname:
                compname = "Purslane Ltd"
            androidappid = cleaned_data['androidappid']
            if not androidappid:
                androidappid = "com.carriez.flutter_hbb"
            compname = compname.replace("&","\\&")

            if all(char.isascii() for char in filename):
                filename = re.sub(r'[^\w\s-]', '_', filename).strip()
                filename = filename.replace(" ","_")
            else:
                filename = "rustdesk"
            if not all(char.isascii() for char in appname):
                appname = "rustdesk"
            if not form.is_valid():
                if is_json:
                    return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
                return render(request, 'generator.html', {'form': form}, status=400)

            myuuid = str(uuid.uuid4())
            full_url = _public_generator_url(request)
            try:
                iconfile = cleaned_data.get('iconfile')
                if not iconfile:
                    iconfile = cleaned_data.get('iconbase64')
                iconlink_url, iconlink_uuid, iconlink_file = save_png(iconfile,myuuid,full_url,"icon.png")
            except:
                print("failed to get icon, using default")
                iconlink_url = "false"
                iconlink_uuid = "false"
                iconlink_file = "false"
            try:
                logofile = cleaned_data.get('logofile')
                if not logofile:
                    logofile = cleaned_data.get('logobase64')
                logolink_url, logolink_uuid, logolink_file = save_png(logofile,myuuid,full_url,"logo.png")
            except:
                print("failed to get logo")
                logolink_url = "false"
                logolink_uuid = "false"
                logolink_file = "false"
            try:
                privacyfile = cleaned_data.get('privacyfile')
                if not privacyfile:
                    privacyfile = cleaned_data.get('privacybase64')
                privacylink_url, privacylink_uuid, privacylink_file = save_png(privacyfile,myuuid,full_url,"privacy.png")
            except:
                print("failed to get logo")
                privacylink_url = "false"
                privacylink_uuid = "false"
                privacylink_file = "false"

            try:
                decodedCustom = build_custom_config(cleaned_data)
            except ValueError as exc:
                if is_json:
                    return JsonResponse({"error": str(exc)}, status=400)
                form.add_error(None, str(exc))
                return render(request, 'generator.html', {'form': form}, status=400)

            decodedCustomJson = json.dumps(decodedCustom, ensure_ascii=True)
            string_bytes = decodedCustomJson.encode("ascii")
            base64_bytes = base64.b64encode(string_bytes)
            encodedCustom = base64_bytes.decode("ascii")

            url = _workflow_url(platform, selfhosted)
            inputs_raw = {
                "server":server,
                "key":key,
                "apiServer":apiServer,
                "custom":encodedCustom,
                "uuid":myuuid,
                "iconlink_url":iconlink_url,
                "iconlink_uuid":iconlink_uuid,
                "iconlink_file":iconlink_file,
                "logolink_url":logolink_url,
                "logolink_uuid":logolink_uuid,
                "logolink_file":logolink_file,
                "privacylink_url":privacylink_url,
                "privacylink_uuid":privacylink_uuid,
                "privacylink_file":privacylink_file,
                "appname":appname,
                "genurl":full_url,
                "urlLink":urlLink,
                "downloadLink":downloadLink,
                "updateLink":updateLink,
                "rdgen":'true',
                "compname": compname,
                "androidappid":androidappid,
                "filename":filename,
                "source_repository": _settings.RUSTDESK_REPOSITORY,
                "source_ref": _source_ref(version),
            }
            for field in PASSTHROUGH_FIELDS:
                value = cleaned_data.get(field)
                if isinstance(value, bool):
                    value = "true" if value else "false"
                inputs_raw[field] = "" if value is None else str(value)

            temp_json_path = f"data_{uuid.uuid4()}.json"
            zip_filename = f"secrets_{uuid.uuid4()}.zip"
            zip_path = "temp_zips/%s" % (zip_filename)
            Path("temp_zips").mkdir(parents=True, exist_ok=True)

            try:
                with open(temp_json_path, "w") as f:
                    json.dump(inputs_raw, f)

                with pyzipper.AESZipFile(
                    zip_path,
                    'w',
                    compression=pyzipper.ZIP_LZMA,
                    encryption=pyzipper.WZ_AES,
                ) as zf:
                    zf.setpassword(_settings.ZIP_PASSWORD.encode())
                    zf.write(temp_json_path, arcname="secrets.json")
            except Exception:
                Path(zip_path).unlink(missing_ok=True)
                return JsonResponse(
                    {"error": "Failed to prepare encrypted build inputs"},
                    status=500,
                )
            finally:
                Path(temp_json_path).unlink(missing_ok=True)

            zipJson = {}
            zipJson['url'] = full_url
            zipJson['file'] = zip_filename

            zip_url = json.dumps(zipJson)

            data = {
                "ref":_settings.GHBRANCH,
                "inputs":{
                    "version":version,
                    "zip_url":zip_url,
                    "source_repository": _settings.RUSTDESK_REPOSITORY,
                    "source_ref": _source_ref(version),
                },
                "return_run_details": True
            } 
            #print(data)
            headers = {
                'Accept':  'application/vnd.github+json',
                'Content-Type': 'application/json',
                'Authorization': 'Bearer '+_settings.GHBEARER,
                'X-GitHub-Api-Version': '2026-03-10'
            }
            new_github_run = GithubRun(
                uuid=myuuid,
                status="Starting generator...please wait"
            )
            try:
                response = requests.post(url, json=data, headers=headers)
                if response.status_code == 200:
                    github_data = response.json()
                    new_github_run.github_run_id = github_data.get('workflow_run_id')
                    if not new_github_run.github_run_id:
                        Path(zip_path).unlink(missing_ok=True)
                        return JsonResponse(
                            {"error": "GitHub did not return a workflow run ID"},
                            status=502,
                        )
                    new_github_run.status = "in_progress"
                    new_github_run.save()

                    if is_json:
                        return JsonResponse(
                            {
                                "uuid": myuuid,
                                "status": new_github_run.status,
                                "workflow_run_id": new_github_run.github_run_id,
                                "log_url": github_data.get('html_url'),
                            },
                            status=202,
                        )
                    return render(request, 'waiting.html', {'filename':filename, 'uuid':myuuid, 'status':"Starting generator...please wait", 'platform':platform, 'log_url': github_data.get('html_url')})
                else:
                    Path(zip_path).unlink(missing_ok=True)
                    return JsonResponse(
                        {
                            "error": "GitHub rejected the start request",
                            "github_status": response.status_code,
                        },
                        status=502,
                    )
            except Exception as e:
                Path(zip_path).unlink(missing_ok=True)
                return JsonResponse({"error": f"Connection error: {str(e)}"}, status=500)
        elif is_json:
            return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
    else:
        form = GenerateForm()
    return render(request, 'generator.html', {'form': form})

def check_for_file(request):
    filename = request.GET.get('filename')
    uuid = request.GET.get('uuid')
    platform = request.GET.get('platform')
    gh_run = get_object_or_404(GithubRun, uuid=uuid)
    github_log_url = f"https://github.com/{_settings.GHUSER}/{_settings.REPONAME}/actions/runs/{gh_run.github_run_id}"

    if gh_run.status not in ['success', 'failure', 'cancelled', 'timed_out', 'skipped']:
        headers = {
            "Authorization": f"Bearer {_settings.GHBEARER}",
            "Accept": "application/vnd.github+json"
        }
        api_url = f"https://api.github.com/repos/{_settings.GHUSER}/{_settings.REPONAME}/actions/runs/{gh_run.github_run_id}"
        
        try:
            gh_response = requests.get(api_url, headers=headers)
            if gh_response.status_code == 200:
                gh_data = gh_response.json()
                
                if gh_data['status'] == 'completed':
                    gh_run.status = gh_data['conclusion']
                    gh_run.save()
        except Exception as e:
            print(f"Error checking GitHub: {e}")
    
    if gh_run.status == "success":
        return render(request, 'generated.html', {
            'filename': filename, 
            'uuid': uuid, 
            'platform': platform
        })
        
    elif gh_run.status in ['failure', 'cancelled', 'timed_out', 'skipped', 'action_required']:
        return render(request, 'failure.html', {
            'log_url': github_log_url, 
            'filename': filename, 
            'uuid': uuid, 
            'platform': platform,
            'status': gh_run.status
        })
        
    else:
        return render(request, 'waiting.html', {
            'filename': filename, 
            'uuid': uuid, 
            'status': gh_run.status, 
            'platform': platform, 
            'log_url': github_log_url
        })

def download(request):
    filename = request.GET['filename']
    uuid = request.GET['uuid']
    file_path = os.path.join('exe', uuid, filename)
    with open(file_path, 'rb') as file:
        content = file.read()
    response = HttpResponse(content, headers={
        'Content-Type': 'application/vnd.microsoft.portable-executable',
        'Content-Disposition': f'attachment; filename="{filename}"'
    })
    return response

def get_png(request):
    filename = request.GET['filename']
    uuid = request.GET['uuid']
    #filename = filename+".exe"
    file_path = os.path.join('png',uuid,filename)
    with open(file_path, 'rb') as file:
        response = HttpResponse(file, headers={
            'Content-Type': 'application/vnd.microsoft.portable-executable',
            'Content-Disposition': f'attachment; filename="{filename}"'
        })

    return response

def create_github_run(myuuid):
    new_github_run = GithubRun(
        uuid=myuuid,
        status="Starting generator...please wait"
    )
    new_github_run.save()

def update_github_run(request):
    data = json.loads(request.body)
    myuuid = data.get('uuid')
    mystatus = data.get('status')
    GithubRun.objects.filter(Q(uuid=myuuid)).update(status=mystatus)
    return HttpResponse('')

def resize_and_encode_icon(imagefile):
    maxWidth = 200
    try:
        with io.BytesIO() as image_buffer:
            for chunk in imagefile.chunks():
                image_buffer.write(chunk)
            image_buffer.seek(0)

            img = Image.open(image_buffer)
            imgcopy = img.copy()
    except (IOError, OSError):
        raise ValueError("Uploaded file is not a valid image format.")

    # Check if resizing is necessary
    if img.size[0] <= maxWidth:
        with io.BytesIO() as image_buffer:
            imgcopy.save(image_buffer, format=imagefile.content_type.split('/')[1])
            image_buffer.seek(0)
            return_image = ContentFile(image_buffer.read(), name=imagefile.name)
        return base64.b64encode(return_image.read())

    # Calculate resized height based on aspect ratio
    wpercent = (maxWidth / float(img.size[0]))
    hsize = int((float(img.size[1]) * float(wpercent)))

    # Resize the image while maintaining aspect ratio using LANCZOS resampling
    imgcopy = imgcopy.resize((maxWidth, hsize), Image.Resampling.LANCZOS)

    with io.BytesIO() as resized_image_buffer:
        imgcopy.save(resized_image_buffer, format=imagefile.content_type.split('/')[1])
        resized_image_buffer.seek(0)

        resized_imagefile = ContentFile(resized_image_buffer.read(), name=imagefile.name)

    # Return the Base64 encoded representation of the resized image
    resized64 = base64.b64encode(resized_imagefile.read())
    #print(resized64)
    return resized64
 
#the following is used when accessed from an external source, like the rustdesk api server
def startgh(request):
    #print(request)
    data_ = json.loads(request.body)
    ####from here run the github action, we need user, repo, access token.
    url = 'https://api.github.com/repos/'+_settings.GHUSER+'/'+_settings.REPONAME+'/actions/workflows/generator-'+data_.get('platform')+'.yml/dispatches'  
    data = {
        "ref": _settings.GHBRANCH,
        "inputs":{
            "server":data_.get('server'),
            "key":data_.get('key'),
            "apiServer":data_.get('apiServer'),
            "custom":data_.get('custom'),
            "uuid":data_.get('uuid'),
            "iconlink":data_.get('iconlink'),
            "logolink":data_.get('logolink'),
            "appname":data_.get('appname'),
            "extras":data_.get('extras'),
            "filename":data_.get('filename')
        }
    } 
    headers = {
        'Accept':  'application/vnd.github+json',
        'Content-Type': 'application/json',
        'Authorization': 'Bearer '+_settings.GHBEARER,
        'X-GitHub-Api-Version': '2026-03-10'
    }
    response = requests.post(url, json=data, headers=headers)
    print(response)
    return HttpResponse(status=204)

def save_png(file, uuid, domain, name):
    file_save_path = "png/%s/%s" % (uuid, name)
    Path("png/%s" % uuid).mkdir(parents=True, exist_ok=True)

    if isinstance(file, str):  # Check if it's a base64 string
        try:
            header, encoded = file.split(';base64,')
            decoded_img = base64.b64decode(encoded)
            file = ContentFile(decoded_img, name=name) # Create a file-like object
        except ValueError:
            print("Invalid base64 data")
            return None  # Or handle the error as you see fit
        except Exception as e:  # Catch general exceptions during decoding
            print(f"Error decoding base64: {e}")
            return None
        
    with open(file_save_path, "wb+") as f:
        for chunk in file.chunks():
            f.write(chunk)
    # imageJson = {}
    # imageJson['url'] = domain
    # imageJson['uuid'] = uuid
    # imageJson['file'] = name
    #return "%s/%s" % (domain, file_save_path)
    return domain, uuid, name

def save_custom_client(request):
    file = request.FILES['file']
    myuuid = request.POST.get('uuid')
    file_save_path = "exe/%s/%s" % (myuuid, file.name)
    Path("exe/%s" % myuuid).mkdir(parents=True, exist_ok=True)
    with open(file_save_path, "wb+") as f:
        for chunk in file.chunks():
            f.write(chunk)

    return HttpResponse("File saved successfully!")

def cleanup_secrets(request):
    # Pass the UUID as a query param or in JSON body
    data = json.loads(request.body)
    my_uuid = data.get('uuid')
    
    if not my_uuid:
        return HttpResponse("Missing UUID", status=400)

    # 1. Find the files in your temp directory matching the UUID
    temp_dir = os.path.join('temp_zips')
    
    # We look for any file starting with 'secrets_' and containing the uuid
    for filename in os.listdir(temp_dir):
        if my_uuid in filename and filename.endswith('.zip'):
            file_path = os.path.join(temp_dir, filename)
            try:
                os.remove(file_path)
                print(f"Successfully deleted {file_path}")
            except OSError as e:
                print(f"Error deleting file: {e}")

    return HttpResponse("Cleanup successful", status=200)

def get_zip(request):
    filename = request.GET['filename']
    #filename = filename+".exe"
    file_path = os.path.join('temp_zips',filename)
    with open(file_path, 'rb') as file:
        response = HttpResponse(file, headers={
            'Content-Type': 'application/vnd.microsoft.portable-executable',
            'Content-Disposition': f'attachment; filename="{filename}"'
        })

    return response
