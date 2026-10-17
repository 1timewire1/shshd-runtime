package org.shshd.runtime;

import android.app.Activity;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.provider.OpenableColumns;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.UUID;

/** Read user-selected documents without broad storage permissions. */
public final class DocumentBridge {
    private DocumentBridge() {}

    public static void choose(final Activity activity, final int request) {
        activity.runOnUiThread(() -> {
            Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
            intent.addCategory(Intent.CATEGORY_OPENABLE);
            // APK/IPA/EXP files are frequently reported as opaque binary data.
            intent.setType("*/*");
            intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            activity.startActivityForResult(intent, request);
        });
    }

    public static String copy(Activity activity, Uri uri, String staging) throws IOException {
        String name = null;
        try (Cursor cursor = activity.getContentResolver().query(uri,
                new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null)) {
            if (cursor != null && cursor.moveToFirst()) name = cursor.getString(0);
        }
        if (name == null) throw new IOException("The document provider did not supply a filename");
        name = name.replace('\\', '/');
        name = name.substring(name.lastIndexOf('/') + 1);
        if (name.isEmpty() || name.equals(".") || name.equals(".."))
            throw new IOException("Invalid document filename");
        File directory = new File(staging, UUID.randomUUID().toString());
        if (!directory.mkdirs()) throw new IOException("Cannot create import directory");
        File target = new File(directory, name);
        boolean complete = false;
        try {
            try (InputStream input = activity.getContentResolver().openInputStream(uri);
                 FileOutputStream output = new FileOutputStream(target)) {
                if (input == null) throw new IOException("Cannot open selected document");
                byte[] buffer = new byte[65536];
                int count;
                while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
            }
            complete = true;
            return target.getAbsolutePath();
        } finally {
            if (!complete) {
                target.delete();
                directory.delete();
            }
        }
    }
}
