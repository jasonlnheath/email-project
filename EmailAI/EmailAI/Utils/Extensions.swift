import Foundation
import SwiftUI

// MARK: - String Extensions

extension String {
    /// Check if string contains HTML tags
    var containsHTMLTags: Bool {
        self.range(of: "<[^>]+>", options: .regularExpression) != nil
    }
}
