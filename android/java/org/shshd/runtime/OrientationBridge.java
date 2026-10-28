package org.shshd.runtime;

import android.app.Activity;
import android.content.pm.ActivityInfo;
import android.view.OrientationEventListener;

/**
 * The side panels want landscape (the owner's rule): turning them on in portrait turns the app to landscape at once,
 * without locking it there. Once the device itself is held in landscape, rotation goes back to the user, so turning
 * it back to portrait rotates the app again, and the host then switches the panels off (platforms/android.py).
 */
public final class OrientationBridge {
    private static OrientationEventListener listener;

    private OrientationBridge() {}

    public static void requestLandscape(final Activity activity) {
        activity.runOnUiThread(new Runnable() {
            @Override
            public void run() {
                stopListening();
                activity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE);
                listener = new OrientationEventListener(activity) {
                    @Override
                    public void onOrientationChanged(int degrees) {
                        // Held sideways (either way round): the device agrees, so the user rotates from here.
                        if (degrees != ORIENTATION_UNKNOWN
                                && ((degrees > 60 && degrees < 120) || (degrees > 240 && degrees < 300))) {
                            stopListening();
                            activity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_FULL_USER);
                        }
                    }
                };
                if (listener.canDetectOrientation()) {
                    listener.enable();
                } else {
                    listener = null;    // no sensor: landscape holds until the panels go off (release)
                }
            }
        });
    }

    /** The panels went off: rotation is the user's again, wherever it was left. */
    public static void release(final Activity activity) {
        activity.runOnUiThread(new Runnable() {
            @Override
            public void run() {
                stopListening();
                activity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_FULL_USER);
            }
        });
    }

    private static void stopListening() {
        if (listener != null) {
            listener.disable();
            listener = null;
        }
    }
}
