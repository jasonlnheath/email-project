import SwiftUI
import GoogleSignIn

@main
struct EmailAIApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @AppStorage("isSignedIn") private var isSignedIn = false

    var body: some Scene {
        WindowGroup {
            Group {
                if isSignedIn {
                    ContentView()
                } else {
                    LoginView()
                }
            }
            .task {
                // Check initial sign-in state from OAuthService
                if !isSignedIn {
                    isSignedIn = await OAuthService.shared.isSignedIn
                }
            }
        }
    }
}

class AppDelegate: NSObject, UIApplicationDelegate {
    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        return true
    }

    // Handle Google Sign-In callback (iOS 9+)
    func application(_ app: UIApplication,
                     open url: URL,
                     options: [UIApplication.OpenURLOptionsKey: Any] = [:]) -> Bool {
        return GIDSignIn.sharedInstance.handle(url)
    }
}
