import XCTest

final class AssistantUITests: XCTestCase {
    func testApprovalResetsAfterEditingAndDisconnectClearsText() {
        let app = XCUIApplication()
        app.launchArguments = ["-AppleLanguages", "(zh-Hans)"]
        app.launch()
        XCTAssertTrue(app.textFields["endpoint"].waitForExistence(timeout: 10))
        let transcript = app.textViews["transcript"]
        for _ in 0..<5 where !transcript.isHittable { app.swipeUp() }
        transcript.tap(); transcript.typeText("synthetic first message")
        let approval = app.switches["approval"]
        for _ in 0..<5 where !approval.isHittable { app.swipeUp() }
        approval.tap()
        XCTAssertEqual(approval.value as? String, "1")
        for _ in 0..<5 where !transcript.isHittable { app.swipeDown() }
        transcript.tap(); transcript.typeText(" updated")
        XCTAssertEqual(approval.value as? String, "0")
        let disconnect = app.buttons["disconnect"]
        for _ in 0..<8 where !disconnect.isHittable { app.swipeDown() }
        disconnect.tap()
        XCTAssertEqual(transcript.value as? String ?? "", "")
        let capture = XCTAttachment(screenshot: app.screenshot()); capture.lifetime = .keepAlways; add(capture)
    }
}
