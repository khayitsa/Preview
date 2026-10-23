package app.feffel.mobile;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Intent;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Base64;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import java.io.IOException;
import java.io.OutputStream;

/**
 * Thin native shell around the hosted Feffel web app.
 *
 * Everything the user sees is the Flask app served from BuildConfig.FEFFEL_URL. This class only adds
 * what a browser tab would normally provide: file picking for uploads, saving downloads (including
 * the in-page "publishing pack" ZIP, which is a blob: URL), the back button, and a retry page when the
 * server cannot be reached.
 */
public class MainActivity extends Activity {

    private static final int REQUEST_FILE = 1;

    private WebView web;
    private ValueCallback<Uri[]> pendingChooser;
    private final Uri home = Uri.parse(BuildConfig.FEFFEL_URL);

    @SuppressLint({"SetJavaScriptEnabled", "AddJavascriptInterface"})
    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        web = new WebView(this);
        web.setLayoutParams(new ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);          // the UI keeps small preferences in localStorage
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setMediaPlaybackRequiresUserGesture(true);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);

        CookieManager cookies = CookieManager.getInstance();
        cookies.setAcceptCookie(true);
        cookies.setAcceptThirdPartyCookies(web, false);

        web.addJavascriptInterface(new DownloadBridge(), "FeffelAndroid");
        web.setWebViewClient(new Client());
        web.setWebChromeClient(new Chrome());
        web.setDownloadListener((url, userAgent, contentDisposition, mimeType, length) ->
                startDownload(url, userAgent, contentDisposition, mimeType));

        if (state != null) {
            web.restoreState(state);
        } else {
            web.loadUrl(home.toString());
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }

    @Override
    protected void onPause() {
        CookieManager.getInstance().flush();   // keep the sign-in across app restarts
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        if (web != null) {
            web.destroy();
        }
        super.onDestroy();
    }

    @SuppressWarnings("deprecation")
    @Override
    public void onBackPressed() {
        if (web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }

    // ---- file picker (post images/videos, avatars, attachments) ---------------------------------

    @SuppressWarnings("deprecation")
    @Override
    protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request != REQUEST_FILE || pendingChooser == null) {
            return;
        }
        Uri[] picked = WebChromeClient.FileChooserParams.parseResult(result, data);
        pendingChooser.onReceiveValue(picked);
        pendingChooser = null;
    }

    private class Chrome extends WebChromeClient {
        @SuppressWarnings("deprecation")
        @Override
        public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback,
                                         FileChooserParams params) {
            if (pendingChooser != null) {
                pendingChooser.onReceiveValue(null);
            }
            pendingChooser = callback;
            try {
                startActivityForResult(params.createIntent(), REQUEST_FILE);
            } catch (ActivityNotFoundException e) {
                pendingChooser = null;
                callback.onReceiveValue(null);
                return false;
            }
            return true;
        }
    }

    // ---- navigation -----------------------------------------------------------------------------

    private class Client extends WebViewClient {
        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            Uri url = request.getUrl();
            if (sameSite(url)) {
                return false;                  // stay inside the app
            }
            if ("blob".equals(url.getScheme()) || "about".equals(url.getScheme())) {
                return false;
            }
            try {                              // external links open in the user's browser / mail app
                startActivity(new Intent(Intent.ACTION_VIEW, url));
            } catch (ActivityNotFoundException ignored) {
                // nothing can open it; ignore
            }
            return true;
        }

        @Override
        public void onPageStarted(WebView view, String url, Bitmap favicon) {
            super.onPageStarted(view, url, favicon);
            view.evaluateJavascript(BLOB_HOOK, null);
        }

        @Override
        public void onPageFinished(WebView view, String url) {
            super.onPageFinished(view, url);
            view.evaluateJavascript(BLOB_HOOK, null);
        }

        @Override
        public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
            if (request.isForMainFrame()) {
                showOfflinePage(view);
            }
        }
    }

    private boolean sameSite(Uri url) {
        return home.getHost() != null && home.getHost().equalsIgnoreCase(url.getHost());
    }

    private void showOfflinePage(WebView view) {
        String page = "<!doctype html><meta charset=utf-8>"
                + "<meta name=viewport content='width=device-width,initial-scale=1'>"
                + "<body style='font:16px system-ui,sans-serif;background:#f6f5fa;color:#1d1b2e;"
                + "display:flex;min-height:90vh;align-items:center;justify-content:center;text-align:center'>"
                + "<div style='max-width:300px'>"
                + "<div style='width:64px;height:64px;border-radius:18px;background:#6957df;margin:0 auto 20px'></div>"
                + "<h2 style='margin:0 0 8px'>Can't reach Feffel</h2>"
                + "<p style='color:#6b6880;margin:0 0 24px'>Check your connection, then try again.</p>"
                + "<a href='" + home + "' style='display:inline-block;background:#6957df;color:#fff;"
                + "padding:12px 28px;border-radius:12px;text-decoration:none;font-weight:600'>Try again</a>"
                + "</div></body>";
        view.loadDataWithBaseURL(home.toString(), page, "text/html", "utf-8", null);
    }

    // ---- downloads ------------------------------------------------------------------------------

    /** Ordinary http(s) downloads (e.g. a media file) go through Android's download manager. */
    private void startDownload(String url, String userAgent, String disposition, String mime) {
        if (url.startsWith("blob:") || url.startsWith("data:")) {
            return;                            // handled in-page by BLOB_HOOK
        }
        try {
            DownloadManager.Request req = new DownloadManager.Request(Uri.parse(url));
            req.addRequestHeader("User-Agent", userAgent);
            String cookie = CookieManager.getInstance().getCookie(url);
            if (cookie != null) {
                req.addRequestHeader("Cookie", cookie);
            }
            String name = URLUtil.guessFileName(url, disposition, mime);
            req.setMimeType(mime);
            req.setTitle(name);
            req.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            req.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, name);
            ((DownloadManager) getSystemService(DOWNLOAD_SERVICE)).enqueue(req);
            toast("Downloading " + name);
        } catch (RuntimeException e) {
            toast("Download failed");
        }
    }

    /**
     * The web app builds its export ZIP in the page (fetch -> Blob -> <a download>.click()). WebView
     * cannot hand a blob: URL to the download manager, so this patches anchor clicks that point at a
     * blob and streams the bytes to FeffelAndroid in chunks instead. Idempotent.
     */
    private static final String BLOB_HOOK = "(function(){"
            + "if(window.__feffelHook||!window.FeffelAndroid)return;window.__feffelHook=true;"
            + "var orig=HTMLAnchorElement.prototype.click;"
            + "HTMLAnchorElement.prototype.click=function(){"
            + " var a=this;"
            + " if(!(a.download&&a.href&&a.href.indexOf('blob:')===0))return orig.call(a);"
            + " fetch(a.href).then(function(r){return r.blob();}).then(function(b){"
            + "  return new Promise(function(done,fail){"
            + "   var fr=new FileReader();"
            + "   fr.onload=function(){"
            + "    var d=String(fr.result),i=d.indexOf(',')+1,n=786432;"  // multiple of 4 -> valid base64 slices
            + "    FeffelAndroid.begin(a.download,b.type||'application/octet-stream');"
            + "    for(var p=i;p<d.length;p+=n)FeffelAndroid.chunk(d.substring(p,p+n));"
            + "    FeffelAndroid.end();done();};"
            + "   fr.onerror=fail;fr.readAsDataURL(b);});"
            + " }).catch(function(){FeffelAndroid.fail();});"
            + "};})();";

    /** Receives the chunks from BLOB_HOOK and writes them to the public Downloads folder. */
    private class DownloadBridge {
        private Uri target;
        private OutputStream out;
        private String name;

        @JavascriptInterface
        public synchronized void begin(String fileName, String mime) {
            close();
            try {
                name = fileName.replaceAll("[\\\\/:*?\"<>|]", "_");
                ContentValues v = new ContentValues();
                v.put(MediaStore.Downloads.DISPLAY_NAME, name);
                v.put(MediaStore.Downloads.MIME_TYPE, mime);
                v.put(MediaStore.Downloads.IS_PENDING, 1);
                ContentResolver cr = getContentResolver();
                target = cr.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, v);
                out = target == null ? null : cr.openOutputStream(target);
            } catch (RuntimeException | IOException e) {
                out = null;
            }
        }

        @JavascriptInterface
        public synchronized void chunk(String base64) {
            if (out == null) {
                return;
            }
            try {
                out.write(Base64.decode(base64, Base64.DEFAULT));
            } catch (IOException | IllegalArgumentException e) {
                abort();
            }
        }

        @JavascriptInterface
        public synchronized void end() {
            if (out == null || target == null) {
                toast("Download failed");
                return;
            }
            try {
                out.close();
                ContentValues v = new ContentValues();
                v.put(MediaStore.Downloads.IS_PENDING, 0);
                getContentResolver().update(target, v, null, null);
                toast("Saved to Downloads: " + name);
            } catch (IOException e) {
                abort();
            } finally {
                out = null;
                target = null;
            }
        }

        @JavascriptInterface
        public synchronized void fail() {
            abort();
        }

        private void abort() {
            close();
            if (target != null) {
                getContentResolver().delete(target, null, null);
                target = null;
            }
            toast("Download failed");
        }

        private void close() {
            if (out != null) {
                try {
                    out.close();
                } catch (IOException ignored) {
                    // already failing
                }
                out = null;
            }
        }
    }

    private void toast(String message) {
        runOnUiThread(() -> Toast.makeText(this, message, Toast.LENGTH_SHORT).show());
    }
}
