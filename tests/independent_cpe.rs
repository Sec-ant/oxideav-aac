//! A fixed external AAC encoder regression, with independent speaker activity.
//! The fixture and both PCM oracles are always present: no external tools or
//! umbrella-repository assets are needed to exercise this test.

use oxideav_aac::decode::StreamDecoder;

#[test]
fn independent_channel_windows_decode_to_reference_pcm() {
    let bytes = include_bytes!("fixtures/independent-cpe/bursts-5.1.aac");
    let frames = StreamDecoder::new()
        .decode_all(bytes)
        .expect("legal AAC common_window=0 channel pairs must decode");
    assert_eq!(frames.len(), 176);
    let mut pcm = Vec::new();
    for (index, frame) in frames.iter().enumerate() {
        assert_eq!(frame.channels, 6, "frame {index}");
        assert_eq!(frame.sample_rate, 48_000, "frame {index}");
        assert_eq!(frame.pcm.len(), 1024 * 6, "frame {index}");
        pcm.extend_from_slice(&frame.pcm);
    }
    assert_eq!(pcm.len(), 180_224 * 6);

    // FFmpeg's s16 output at every 256th sample in canonical 5.1 order.
    // This pins waveform, timing, polarity, and speaker order independently
    // of this decoder, without storing the entire 2 MiB reference waveform.
    let expected = include_bytes!("fixtures/independent-cpe/expected-probes.s16le");
    let probes = pcm.chunks_exact(6).step_by(256);
    assert_eq!(expected.len(), probes.len() * 6 * 2);
    for (index, (actual, reference)) in probes.zip(expected.chunks_exact(12)).enumerate() {
        for channel in 0..6 {
            let reference =
                i16::from_le_bytes([reference[channel * 2], reference[channel * 2 + 1]]);
            let error = (i32::from(actual[channel]) - i32::from(reference)).abs();
            assert!(
                error <= 8,
                "sample {} channel {channel}: error {error} LSB",
                index * 256
            );
        }
    }

    // Every 512-sample window, including silent channels and overlap tails,
    // has an independent reference energy. 2 LSB accommodates IMDCT/PCM
    // rounding and the fixture's tiny PNS contribution; activity misplaced
    // in time or routed to a different channel cannot hide in a global RMS.
    let expected = include_bytes!("fixtures/independent-cpe/expected-rms.f32le");
    assert_eq!(expected.len(), (180_224 / 512) * 6 * 4);
    for (window, actual) in pcm.chunks_exact(512 * 6).enumerate() {
        for channel in 0..6 {
            let energy: f64 = actual
                .iter()
                .skip(channel)
                .step_by(6)
                .map(|&sample| f64::from(sample).powi(2))
                .sum();
            let actual_rms = (energy / 512.0).sqrt();
            let pos = (window * 6 + channel) * 4;
            let reference = f64::from(f32::from_le_bytes(
                expected[pos..pos + 4].try_into().unwrap(),
            ));
            assert!(
                (actual_rms - reference).abs() <= 2.0,
                "window {window} channel {channel}: RMS {actual_rms} vs {reference}"
            );
        }
    }
}
