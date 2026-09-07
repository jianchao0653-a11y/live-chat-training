import Foundation
import Security

struct DeviceConnection: Codable { let endpoint: String; let token: String }
enum DeviceVault {
    private static let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: "com.conversationlens.device", kSecAttrAccount as String: "paired"]
    static func save(_ value: DeviceConnection) throws {
        let data = try JSONEncoder().encode(value)
        let status = SecItemUpdate(query as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if status == errSecItemNotFound {
            var insert = query; insert[kSecValueData as String] = data; insert[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
            guard SecItemAdd(insert as CFDictionary, nil) == errSecSuccess else { throw LensError.message("无法保存设备凭据") }
        } else if status != errSecSuccess { throw LensError.message("无法更新设备凭据") }
    }
    static func load() -> DeviceConnection? {
        var q = query; q[kSecReturnData as String] = true; q[kSecMatchLimit as String] = kSecMatchLimitOne
        var value: CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary, &value) == errSecSuccess, let data = value as? Data else { return nil }
        return try? JSONDecoder().decode(DeviceConnection.self, from: data)
    }
    static func clear() { SecItemDelete(query as CFDictionary) }
}
