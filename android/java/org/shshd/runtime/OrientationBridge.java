package org.shshd.runtime;

import android.app.Activity;
import android.content.pm.ActivityInfo;
import android.view.OrientationEventListener;

/**
 * The side panels want landscape (the owner's rule): turning them on in portrait turns the app to landscape at once,
 * without locking it there. Once the device itself is held in landscape, the app follows the device again, so turning
 * it back to portrait rotates the app, the host then switches the panels off (platforms/android.py), and rotation is
 * the user's setting again.
 */
public final class OrientationBridge {
    private static OrientationEventListener listener;
    private static volatile boolean holding;    // landscape asked for, the device not yet turned
    private static volatile boolean following;  // turned: the app follows the device until the panels go off

    private OrientationBridge() {}

    public static void requestLandscape(final Activity activity) {
        activity.runOnUiThread(new Runnable() {
            @Override
            public void run() {
                stopListening();
                holding = true;
                following = false;
                activity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE);
                listener = new OrientationEventListener(activity) {
                    @Override
                    public void onOrientationChanged(int degrees) {
                        // Held sideways (either way round): the device agrees, so it rotates as it is held from here
                        // (the sensor, not the user's rotation lock, which would turn it straight back to portrait),
                        // and turning it back to portrait is what switches the panels off.
                        if (degrees != ORIENTATION_UNKNOWN
                                && ((degrees > 60 && degrees < 120) || (degrees > 240 && degrees < 300))) {
                            stopListening();
                            holding = false;
                            following = true;
                            activity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_FULL_SENSOR);
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

    /** Whether landscape is still held (the host then has SDL ask for landscape too when it remakes the window). */
    public static boolean isHolding() {
        return holding;
    }

    /**
     * SDL asks for its own orientation whenever the window is remade (FULL_USER: the user's rotation lock), which
     * would turn the app back to portrait while the panels follow the device: ask again for this bridge's.
     */
    public static void afterWindow(final Activity activity) {
        activity.runOnUiThread(new Runnable() {
            @Override
            public void run() {
                if (holding) {
                    activity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE);
                } else if (following) {
                    activity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_FULL_SENSOR);
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
                holding = false;
                following = false;
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
